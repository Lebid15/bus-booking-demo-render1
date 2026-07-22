from django.urls import path

from notifications.views import (
    MeNotificationListView,
    MeNotificationPreferenceView,
    MeNotificationReadView,
    MePushSubscriptionView,
    OfficeNotificationListView,
    PlatformNotificationDeliveryListView,
    PlatformNotificationDeliveryRetryView,
)

urlpatterns = [
    path("me/notifications", MeNotificationListView.as_view()),
    path("me/notifications/preferences", MeNotificationPreferenceView.as_view()),
    path("me/notifications/<str:notification_id>/read", MeNotificationReadView.as_view()),
    path("me/push-subscriptions", MePushSubscriptionView.as_view()),
    path("office/notifications", OfficeNotificationListView.as_view()),
    path("platform/notification-deliveries", PlatformNotificationDeliveryListView.as_view()),
    path(
        "platform/notification-deliveries/<str:delivery_id>/retry",
        PlatformNotificationDeliveryRetryView.as_view(),
    ),
]
