"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import logging

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

logger = logging.getLogger(__name__)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # API
    path("api/", include("config.api_urls")),
    # Social Authentication
    path("api/auth/social/", include("social_django.urls", namespace="social")),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

# Prometheus metrics endpoint (if available)
try:
    from apps.core.monitoring import MetricsView

    urlpatterns += [
        path("metrics/", MetricsView.as_view(), name="prometheus-metrics"),
    ]
    logger.info("Prometheus metrics endpoint enabled at /metrics/")
except ImportError:
    logger.warning(
        "Prometheus client not available - metrics endpoint disabled. "
        "Install prometheus-client to enable: pip install prometheus-client"
    )

# Add debug toolbar in development
if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns += [
            path("__debug__/", include(debug_toolbar.urls)),
        ]
    except ImportError:
        logger.warning("Django Debug Toolbar not installed")
