from django.urls import path

from fleet.views import (
    DriverDetailView,
    DriverListCreateView,
    SeatLayoutDetailView,
    SeatLayoutListCreateView,
    VehicleDetailView,
    VehicleListCreateView,
)

urlpatterns = [
    path("office/seat-layouts", SeatLayoutListCreateView.as_view(), name="office-seat-layouts"),
    path(
        "office/seat-layouts/<str:layout_id>",
        SeatLayoutDetailView.as_view(),
        name="office-seat-layout-detail",
    ),
    path("office/vehicles", VehicleListCreateView.as_view(), name="office-vehicles"),
    path(
        "office/vehicles/<str:vehicle_id>",
        VehicleDetailView.as_view(),
        name="office-vehicle-detail",
    ),
    path("office/drivers", DriverListCreateView.as_view(), name="office-drivers"),
    path(
        "office/drivers/<str:driver_id>",
        DriverDetailView.as_view(),
        name="office-driver-detail",
    ),
]
