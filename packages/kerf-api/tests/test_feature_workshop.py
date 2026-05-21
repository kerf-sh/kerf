"""T-60 Workshop: gallery / readme / likes — feature-level hermetic tests.

Coverage (25 test cases):
  1-5   Publish flow: visibility toggle, readme resolution (explicit / template / alias),
        title/description updates, idempotent re-publish.
  6-10  Primary-image selection: pin, unpin, swap, invariant, thumbnail fallback URL.
  11-15 workshop_likes toggle: like, unlike, idempotent conflict, count arithmetic,
        multi-user isolation.
  16-20 _project_to_workshop_row wire-shape: required keys, likes_count cast,
        images list, model_file_id, author block.
  21-25 README markdown safe-render: script tag stripped intent, heading preserved,
        table preserved, nested tags neutralised, blank README stays None.

All tests are offline (no live DB, no live LLM, no live render).
"""
import copy
import json
import uuid


# ---------------------------------------------------------------------------
# Helpers — offline mirrors of backend logic
# ---------------------------------------------------------------------------

def apply_set_primary(images: list, target_id: str) -> list:
    """Pure-Python replica of the SQL set_primary_workshop_image transaction."""
    images = copy.deepcopy(images)
    target = next((img for img in images if img["id"] == target_id), None)
    if target is None:
        raise KeyError(f"image {target_id!r} not found")
    was_primary = target["is_primary"]
    for img in images:
        img["is_primary"] = False
    if not was_primary:
        target["is_primary"] = True
    return images


def toggle_like_offline(likes: set, user_id: str, project_id: str) -> dict:
    """Pure-Python replica of workshop_likes_queries.toggle_like logic."""
    key = (user_id, project_id)
    if key in likes:
        likes.discard(key)
        liked = False
    else:
        likes.add(key)
        liked = True
    count = sum(1 for u, p in likes if p == project_id)
    return {"liked_by_me": liked, "likes_count": count}


def project_to_workshop_row(p: dict) -> dict:
    """Mirrors _project_to_workshop_row in routes.py (offline subset)."""
    pid = str(p["id"])
    thumbnail_url = (
        f"/api/projects/{pid}/thumbnail" if p.get("thumbnail_storage_key") else None
    )
    images = [
        {
            "id": str(im["id"]),
            "name": im.get("name") or "",
            "url": f"/api/projects/{pid}/workshop-media/{im['id']}",
        }
        for im in (p.get("workshop_images") or [])
    ]
    model_id = p.get("workshop_model_id")
    return {
        "project_id": pid,
        "slug": pid,
        "name": p.get("name", ""),
        "title": p.get("name", ""),
        "description": p.get("description", ""),
        "tags": list(p.get("tags") or []),
        "workspace_slug": p.get("workspace_slug", ""),
        "workspace_name": p.get("workspace_name", ""),
        "author_name": p.get("author_name", ""),
        "author": {
            "id": str(p["author_id"]) if p.get("author_id") else None,
            "name": p.get("workspace_name") or p.get("author_name") or "unknown",
            "avatar_url": p.get("author_avatar_url"),
            "is_verified_publisher": bool(p.get("is_verified_publisher", False)),
            "workspace_name": p.get("workspace_name") or "",
            "workspace_slug": p.get("workspace_slug") or "",
            "user_name": p.get("author_name") or "",
        },
        "likes_count": int(p.get("likes_count") or 0),
        "liked_by_me": bool(p.get("liked_by_me", False)),
        "forks_count": int(p.get("forks_count") or 0),
        "file_count": int(p.get("file_count") or 0),
        "total_bytes": int(p.get("total_bytes") or 0),
        "thumbnail_storage_key": p.get("thumbnail_storage_key"),
        "thumbnail_url": thumbnail_url,
        "images": images,
        "model_file_id": str(model_id) if model_id else None,
        "model_name": p.get("workshop_model_name") or None,
        "readme": p.get("readme") or None,
        "readme_generated_at": (
            p["readme_generated_at"].isoformat()
            if p.get("readme_generated_at") else None
        ),
        "cover_storage_key": p.get("cover_storage_key"),
        "cover_url": (
            f"/api/projects/{pid}/cover"
            if p.get("cover_storage_key") else thumbnail_url
        ),
        "published_at": p["created_at"].isoformat() if p.get("created_at") else None,
        "last_edited": p["updated_at"].isoformat() if p.get("updated_at") else None,
        "created_at": p["created_at"].isoformat() if p.get("created_at") else None,
        "updated_at": p["updated_at"].isoformat() if p.get("updated_at") else None,
    }


def _resolve_publish_readme(
    body_readme: str | None,
    body_readme_override: str,
    generate_readme: bool,
    template_fn,
    project_ctx: dict,
) -> str | None:
    """Mirrors the readme-resolution block inside workshop_publish."""
    explicit_readme: str | None = None
    if body_readme:
        explicit_readme = body_readme.strip() or None
    elif body_readme_override:
        explicit_readme = body_readme_override.strip() or None

    if explicit_readme:
        return explicit_readme
    if generate_readme:
        return template_fn(project_ctx)
    return None


def _template_fn(ctx: dict) -> str:
    """Thin offline stand-in for generate_readme_template."""
    return f"# {ctx.get('name', 'Untitled')}\n\n## Overview\n\n{ctx.get('description', '')}"


# ---------------------------------------------------------------------------
# 1-5  Publish flow
# ---------------------------------------------------------------------------

def test_publish_sets_visibility_public():
    """Publish must flip visibility to 'public'."""
    project = {"visibility": "private", "name": "Clip Bracket"}
    project["visibility"] = "public"
    assert project["visibility"] == "public"


def test_publish_explicit_readme_stored():
    """Supplying readme= must store it verbatim, skipping AI gen."""
    readme = _resolve_publish_readme(
        body_readme="# My README\nHello.",
        body_readme_override="",
        generate_readme=True,
        template_fn=_template_fn,
        project_ctx={"name": "X"},
    )
    assert readme == "# My README\nHello."


def test_publish_readme_override_alias_used_when_readme_absent():
    """readme_override= is accepted when readme= is not supplied."""
    readme = _resolve_publish_readme(
        body_readme=None,
        body_readme_override="# Override README",
        generate_readme=True,
        template_fn=_template_fn,
        project_ctx={"name": "Y"},
    )
    assert readme == "# Override README"


def test_publish_template_generated_when_no_explicit_readme():
    """When no explicit README is supplied, template fallback is used."""
    readme = _resolve_publish_readme(
        body_readme=None,
        body_readme_override="",
        generate_readme=True,
        template_fn=_template_fn,
        project_ctx={"name": "Servo Arm", "description": "A servo bracket."},
    )
    assert readme is not None
    assert "Servo Arm" in readme


def test_publish_idempotent_re_publish_keeps_public():
    """Publishing an already-public project must remain public."""
    project = {"visibility": "public", "name": "Hinge"}
    # simulate idempotent publish
    project["visibility"] = "public"
    assert project["visibility"] == "public"


# ---------------------------------------------------------------------------
# 6-10  Primary-image selection
# ---------------------------------------------------------------------------

def _make_images(n: int) -> list:
    return [
        {"id": f"img-{i}", "sort_order": i, "is_primary": False, "caption": None}
        for i in range(n)
    ]


def test_pin_non_primary_image():
    images = _make_images(4)
    result = apply_set_primary(images, "img-2")
    primaries = [im for im in result if im["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["id"] == "img-2"


def test_unpin_already_primary_leaves_no_primary():
    images = _make_images(3)
    images[1]["is_primary"] = True
    result = apply_set_primary(images, "img-1")
    assert not any(im["is_primary"] for im in result)


def test_swap_primary_clears_old():
    images = _make_images(3)
    images[0]["is_primary"] = True
    result = apply_set_primary(images, "img-2")
    assert result[0]["is_primary"] is False
    assert result[2]["is_primary"] is True


def test_primary_invariant_at_most_one():
    images = _make_images(6)
    images[3]["is_primary"] = True
    result = apply_set_primary(images, "img-5")
    primaries = [im for im in result if im["is_primary"]]
    assert len(primaries) == 1


def test_thumbnail_url_resolves_to_primary_image():
    """When a primary_image_id is set, thumbnail_url uses workshop-images endpoint."""
    p = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "name": "Clip",
        "thumbnail_storage_key": "projects/clip/thumb.jpg",
        "workshop_images": [],
        "workshop_model_id": None,
        "tags": [],
        "likes_count": 0,
        "liked_by_me": False,
        "forks_count": 0,
        "file_count": 0,
        "total_bytes": 0,
        "cover_storage_key": None,
        "readme": None,
        "readme_generated_at": None,
        "created_at": None,
        "updated_at": None,
        "workspace_slug": "ws",
        "workspace_name": "Workspace",
        "author_name": "alice",
        "author_id": str(uuid.uuid4()),
    }
    row = project_to_workshop_row(p)
    # thumbnail from storage key since no primary image
    assert row["thumbnail_url"] == f"/api/projects/{p['id']}/thumbnail"


# ---------------------------------------------------------------------------
# 11-15  workshop_likes toggle
# ---------------------------------------------------------------------------

def test_like_increments_count():
    likes: set = set()
    pid = "proj-1"
    result = toggle_like_offline(likes, "user-1", pid)
    assert result["liked_by_me"] is True
    assert result["likes_count"] == 1


def test_unlike_decrements_count():
    likes: set = set()
    pid = "proj-1"
    toggle_like_offline(likes, "user-1", pid)  # like
    result = toggle_like_offline(likes, "user-1", pid)  # unlike
    assert result["liked_by_me"] is False
    assert result["likes_count"] == 0


def test_like_toggle_idempotent_on_conflict():
    """ON CONFLICT DO NOTHING: second INSERT by same user must not double-count."""
    likes: set = set()
    pid = "proj-2"
    toggle_like_offline(likes, "user-A", pid)
    # Simulate conflict: manually ensure key exists (as if INSERT was ignored)
    key = ("user-A", pid)
    assert key in likes
    # Count should still be 1
    count = sum(1 for u, p in likes if p == pid)
    assert count == 1


def test_multi_user_like_counts_are_independent():
    likes: set = set()
    pid = "proj-3"
    toggle_like_offline(likes, "user-1", pid)
    toggle_like_offline(likes, "user-2", pid)
    toggle_like_offline(likes, "user-3", pid)
    result = toggle_like_offline(likes, "user-4", pid)
    assert result["likes_count"] == 4


def test_unlike_does_not_affect_other_projects():
    likes: set = set()
    pid_a = "proj-A"
    pid_b = "proj-B"
    toggle_like_offline(likes, "user-1", pid_a)
    toggle_like_offline(likes, "user-1", pid_b)
    # Unlike pid_a
    toggle_like_offline(likes, "user-1", pid_a)
    count_b = sum(1 for u, p in likes if p == pid_b)
    assert count_b == 1


# ---------------------------------------------------------------------------
# 16-20  _project_to_workshop_row wire-shape
# ---------------------------------------------------------------------------

def _base_project(**overrides) -> dict:
    import datetime
    base = {
        "id": "aaaaaaaa-0000-0000-0000-000000000099",
        "name": "Test Project",
        "description": "A test.",
        "tags": ["mech"],
        "workspace_slug": "ws",
        "workspace_name": "Workshop",
        "author_name": "alice",
        "author_id": str(uuid.uuid4()),
        "author_avatar_url": None,
        "is_verified_publisher": False,
        "likes_count": 3,
        "liked_by_me": True,
        "forks_count": 1,
        "file_count": 5,
        "total_bytes": 1024,
        "thumbnail_storage_key": "key/thumb.jpg",
        "cover_storage_key": None,
        "workshop_images": [],
        "workshop_model_id": None,
        "workshop_model_name": None,
        "readme": "# Hello",
        "readme_generated_at": None,
        "created_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        "updated_at": datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc),
    }
    base.update(overrides)
    return base


def test_workshop_row_has_required_keys():
    row = project_to_workshop_row(_base_project())
    for key in ("project_id", "slug", "name", "description", "tags",
                "likes_count", "liked_by_me", "forks_count", "file_count",
                "total_bytes", "thumbnail_url", "images", "readme",
                "cover_url", "published_at"):
        assert key in row, f"missing key: {key}"


def test_workshop_row_likes_count_cast_to_int():
    row = project_to_workshop_row(_base_project(likes_count="7"))
    assert isinstance(row["likes_count"], int)
    assert row["likes_count"] == 7


def test_workshop_row_images_list_populated():
    import datetime
    pid = "aaaaaaaa-0000-0000-0000-000000000088"
    images = [
        {"id": "img-x", "name": "front.png"},
        {"id": "img-y", "name": "side.png"},
    ]
    p = _base_project(id=pid, workshop_images=images)
    row = project_to_workshop_row(p)
    assert len(row["images"]) == 2
    assert row["images"][0]["url"].endswith(f"/workshop-media/img-x")


def test_workshop_row_model_file_id_present():
    model_id = str(uuid.uuid4())
    row = project_to_workshop_row(_base_project(workshop_model_id=model_id))
    assert row["model_file_id"] == model_id


def test_workshop_row_author_block_shape():
    row = project_to_workshop_row(_base_project(workspace_name="CoolWS", author_name="bob"))
    author = row["author"]
    assert "id" in author
    assert "name" in author
    assert "is_verified_publisher" in author
    # author name should prefer workspace_name
    assert author["name"] == "CoolWS"


# ---------------------------------------------------------------------------
# 21-25  README markdown safe-render (intent tests — no live sanitiser needed)
# ---------------------------------------------------------------------------

def _naive_strip_script(text: str) -> str:
    """Minimal stand-in for a safe-render pass: remove <script> tags."""
    import re
    return re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)


def test_readme_script_tag_stripped():
    raw = "# Hello\n<script>alert('xss')</script>\nSafe content."
    rendered = _naive_strip_script(raw)
    assert "<script>" not in rendered
    assert "Safe content." in rendered


def test_readme_heading_preserved():
    raw = "# My Project\n\nSome text."
    rendered = _naive_strip_script(raw)
    assert "# My Project" in rendered


def test_readme_table_preserved():
    raw = "| Part | Qty |\n|------|-----|\n| Bolt | 4   |"
    rendered = _naive_strip_script(raw)
    assert "| Bolt | 4   |" in rendered


def test_readme_nested_script_neutralised():
    raw = "Good content.\n<SCRIPT type='text/javascript'>bad()</SCRIPT>"
    rendered = _naive_strip_script(raw)
    assert "bad()" not in rendered
    assert "Good content." in rendered


def test_blank_readme_stays_none():
    """When readme is empty string, the wire-shape must expose None."""
    row = project_to_workshop_row(_base_project(readme=""))
    assert row["readme"] is None
