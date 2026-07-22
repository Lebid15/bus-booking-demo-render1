from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionBearerAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "identity.authentication.SessionBearerAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):  # type: ignore[no-untyped-def]
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
