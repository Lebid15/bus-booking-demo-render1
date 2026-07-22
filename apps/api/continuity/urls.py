from django.urls import path

from continuity.views import (
    ContinuityCommandView,
    ContinuityOverviewView,
    IncidentCommandView,
    IncidentListCreateView,
    LoadTestView,
    RecoveryExerciseView,
    ReleaseRunView,
)

urlpatterns = [
    path("platform/continuity", ContinuityOverviewView.as_view()),
    path("platform/continuity/commands", ContinuityCommandView.as_view()),
    path("platform/continuity/recovery-exercises", RecoveryExerciseView.as_view()),
    path("platform/releases", ReleaseRunView.as_view()),
    path("platform/incidents", IncidentListCreateView.as_view()),
    path("platform/incidents/<str:incident_id>/commands", IncidentCommandView.as_view()),
    path("platform/load-tests", LoadTestView.as_view()),
]
