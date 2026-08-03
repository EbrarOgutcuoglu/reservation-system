from django.contrib import admin

from .models import Reservation, Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "resource", "start_time", "end_time", "status")
    list_filter = ("status", "resource")
    search_fields = ("user__username", "resource__name")
