"""
Tests for Forge schema registry.
"""

from djangoforge.api.schema import EndpointMeta, SchemaRegistry, openapi_meta, schema_registry


class TestSchemaRegistry:
    def test_register_and_get(self):
        reg = SchemaRegistry()
        meta = EndpointMeta(operation_id="listUsers", tags=["users"])
        reg.register("/api/v1/users", meta)
        assert reg.get("/api/v1/users") is meta
        assert reg.get("/missing") is None

    def test_all(self):
        reg = SchemaRegistry()
        reg.register("/a", EndpointMeta())
        reg.register("/b", EndpointMeta())
        assert len(reg.all()) == 2

    def test_validate_missing_operation_id(self):
        reg = SchemaRegistry()
        reg.register("/x", EndpointMeta(tags=["t"], responses={200: "OK"}))
        issues = reg.validate()
        assert any("operationId" in i for i in issues)

    def test_validate_passes_with_full_meta(self):
        reg = SchemaRegistry()
        reg.register("/y", EndpointMeta(operation_id="op1", tags=["t"], responses={200: "OK"}))
        issues = reg.validate()
        assert not issues


class TestOpenApiMeta:
    def test_registers_and_returns(self):
        meta = openapi_meta("/api/test", operation_id="test_op", tags=["test"], responses={200: "OK"})
        assert meta.operation_id == "test_op"
        assert schema_registry.get("/api/test") is meta
