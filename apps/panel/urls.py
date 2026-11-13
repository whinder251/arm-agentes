from django.urls import path
from apps.panel import views

urlpatterns = [
    path('', views.lista_tareas, name='lista_tareas'),
    path('tarea/nueva/', views.crear_tarea, name='crear_tarea'),
    path('tarea/<int:pk>/', views.detalle_tarea, name='detalle_tarea'),
    path('aprobar/', views.aprobar_tarea, name='aprobar_tarea'),
    path('login/', views.login_panel, name='login_panel'),
    path('logout/', views.logout_panel, name='logout_panel'),
    path('configuracion/', views.configuracion, name='configuracion'),
    path('configuracion/proveedor/nuevo/', views.crear_proveedor, name='crear_proveedor'),
    path('configuracion/modelo/nuevo/', views.crear_modelo, name='crear_modelo'),
    path('configuracion/habilidad/nuevo/', views.crear_habilidad, name='crear_habilidad'),
    path('configuracion/agente/nuevo/', views.crear_agente, name='crear_agente'),
    path('configuracion/habilidades/', views.lista_habilidades, name='lista_habilidades'),
    path('configuracion/habilidades/<int:pk>/editar/', views.editar_habilidad, name='editar_habilidad'),
    path('configuracion/habilidades/<int:pk>/eliminar/', views.eliminar_habilidad, name='eliminar_habilidad'),
    path('configuracion/agentes/', views.lista_agentes, name='lista_agentes'),
    path('configuracion/agentes/<int:pk>/editar/', views.editar_agente, name='editar_agente'),
    path('configuracion/agentes/<int:pk>/eliminar/', views.eliminar_agente, name='eliminar_agente'),
]
