from django.urls import path
from apps.panel import views

urlpatterns = [
    path('', views.lista_tareas, name='lista_tareas'),
    path('tarea/<int:pk>/', views.detalle_tarea, name='detalle_tarea'),
    path('aprobar/', views.aprobar_tarea, name='aprobar_tarea'),
]
