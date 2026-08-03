from django.urls import path

from . import views

urlpatterns = [
    path("", views.api_home),
    path("auth/register/", views.register),
    path("auth/login/", views.login),
    path("profile/", views.profile),
    path("resources/", views.resource_list),
    path("availability/", views.availability),
    path("holds/", views.hold_reservation_slot),
    path("holds/release/", views.release_reservation_hold),
    path("reservations/", views.reservation_list_create),
    path("reservations/<int:reservation_id>/", views.reservation_detail),
    path("events/", views.event_stream),
    path("admin/reservations/", views.admin_reservations),
    path("admin/reservations/<int:reservation_id>/status/", views.admin_change_status),
    path("admin/users/", views.admin_users),
]
