"""
Tests for Forge API contract types.
"""

from djangoforge.api.contracts import (
    ApiResponse,
    FilterSpec,
    PaginationSpec,
    ProblemDetail,
    RequestContext,
    SortSpec,
)


class TestRequestContext:
    def test_defaults(self):
        ctx = RequestContext()
        assert ctx.user_id is None
        assert ctx.correlation_id == ""
        assert ctx.permissions == []
        assert ctx.groups == []
        assert ctx.scopes == []

    def test_custom_values(self):
        ctx = RequestContext(
            user_id="u1",
            email="a@b.com",
            tenant="t1",
            correlation_id="cid-1",
            groups=["admin"],
            scopes=["read"],
            auth_provider="google",
        )
        assert ctx.user_id == "u1"
        assert ctx.tenant == "t1"
        assert ctx.groups == ["admin"]


class TestProblemDetail:
    def test_defaults(self):
        pd = ProblemDetail()
        assert pd.status == 500
        assert pd.type == "about:blank"

    def test_custom(self):
        pd = ProblemDetail(title="Not Found", status=404, detail="Resource missing")
        assert pd.status == 404
        assert pd.title == "Not Found"


class TestPaginationSpec:
    def test_defaults(self):
        ps = PaginationSpec()
        assert ps.page == 1
        assert ps.page_size == 20
        assert ps.cursor is None


class TestFilterSpec:
    def test_defaults(self):
        fs = FilterSpec()
        assert fs.operator == "eq"


class TestSortSpec:
    def test_defaults(self):
        ss = SortSpec()
        assert ss.direction == "asc"


class TestApiResponse:
    def test_ok_when_no_errors(self):
        resp = ApiResponse(data={"key": "value"})
        assert resp.ok is True
        assert resp.data == {"key": "value"}

    def test_not_ok_with_errors(self):
        resp = ApiResponse(errors=[ProblemDetail(status=400)])
        assert resp.ok is False
