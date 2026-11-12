"""Tests de la reserva atómica de cuota diaria."""

import threading
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

import apps.providers.quota as quota_module
from apps.core.models import ContadorCuota, Proveedor
from apps.providers.quota import CuotaDiaria


def crear_proveedor(**extra):
    datos = {
        "nombre": "Proveedor de prueba",
        "base_url": "https://example.invalid/v1",
        "limite_diario": 3,
    }
    datos.update(extra)
    return Proveedor.objects.create(**datos)


@pytest.mark.django_db
def test_tres_reservas_y_la_cuarta_se_rechaza():
    proveedor = crear_proveedor(limite_diario=3)
    cuota = CuotaDiaria(proveedor)

    assert [cuota.reservar() for _ in range(3)] == [True, True, True]
    assert cuota.reservar() is False

    contador = ContadorCuota.objects.get(proveedor=proveedor)
    assert contador.usadas == 3


@pytest.mark.django_db
def test_limite_cero_significa_sin_limite():
    proveedor = crear_proveedor(nombre="Sin límite", limite_diario=0)
    cuota = CuotaDiaria(proveedor)

    assert [cuota.reservar() for _ in range(5)] == [True] * 5
    assert ContadorCuota.objects.filter(proveedor=proveedor).count() == 0


@pytest.mark.django_db
def test_liberar_devuelve_la_reserva_y_permite_volver_a_reservar():
    proveedor = crear_proveedor(nombre="Con liberación", limite_diario=1)
    cuota = CuotaDiaria(proveedor)

    assert cuota.reservar() is True
    assert cuota.reservar() is False

    assert cuota.liberar() is True
    assert cuota.reservar() is True
    assert cuota.liberar() is True
    assert cuota.liberar() is False

    contador = ContadorCuota.objects.get(proveedor=proveedor)
    assert contador.usadas == 0


@pytest.mark.django_db
def test_el_contador_se_reinicia_al_cambiar_de_dia(monkeypatch):
    proveedor = crear_proveedor(nombre="Cambio de día", limite_diario=1)
    cuota = CuotaDiaria(proveedor)

    assert cuota.reservar() is True
    assert cuota.reservar() is False

    manana = timezone.localdate() + timedelta(days=1)
    monkeypatch.setattr(quota_module.timezone, "localdate", lambda: manana)

    assert cuota.reservar() is True
    assert ContadorCuota.objects.filter(proveedor=proveedor).count() == 2


@pytest.mark.django_db(transaction=True)
def test_dos_hilos_solo_consiguen_una_reserva():
    proveedor = crear_proveedor(nombre="Proveedor concurrente", limite_diario=1)
    barrera = threading.Barrier(2)
    resultados = []
    errores = []
    candado = threading.Lock()

    def trabajador():
        try:
            barrera.wait(timeout=5)
            actual = Proveedor.objects.get(pk=proveedor.pk)
            resultado = CuotaDiaria(actual).reservar()
            with candado:
                resultados.append(resultado)
        except Exception as error:
            with candado:
                errores.append(error)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=trabajador, daemon=True) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=10)

    assert [hilo.is_alive() for hilo in hilos] == [False, False]
    assert errores == []
    assert sorted(resultados) == [False, True]
    assert ContadorCuota.objects.get(proveedor=proveedor).usadas == 1
