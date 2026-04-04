from __future__ import annotations

import json

from pipeline_contracts.models import (
    ContentPackage,
    IdentityMatrix,
    VideoBlueprint,
)
from pipeline_contracts.models.identity import AvatarPackRef, PersonaAxis, VoicePackRef


def test_identity_roundtrip() -> None:
    im = IdentityMatrix(
        matrix_id="m1",
        display_name="D",
        niche="n",
        persona=PersonaAxis(tone="t"),
        avatar=AvatarPackRef(avatar_id="a1"),
        voice=VoicePackRef(voice_id="v1"),
    )
    raw = im.model_dump(mode="json")
    im2 = IdentityMatrix.model_validate(raw)
    assert im2.matrix_id == "m1"


def test_blueprint_and_package_roundtrip() -> None:
    vb = VideoBlueprint(
        blueprint_id="b1",
        matrix_id="m1",
        title="T",
        hook="H",
    )
    s = json.dumps(vb.model_dump(mode="json"))
    VideoBlueprint.model_validate_json(s)

    from pipeline_contracts.models.content import MediaAssetRef

    cp = ContentPackage(
        package_id="p1",
        run_id="r1",
        blueprint_id="b1",
        matrix_id="m1",
        primary_video=MediaAssetRef(path="/tmp/x.mp4"),
        caption="c",
    )
    ContentPackage.model_validate(cp.model_dump(mode="json"))
