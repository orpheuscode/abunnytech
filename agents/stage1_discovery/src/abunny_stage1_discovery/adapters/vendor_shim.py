"""Named stub adapters matching `analysis_ports` (TwelveLabs / Gemini style).

Production replaces these with SDK-backed implementations; offline runs use
`FixtureAnalysisPipeline` or these thin delegators.
"""

from __future__ import annotations

from abunny_stage1_discovery.analysis_enums import CtaKind, HookLabel, ProductIntegration
from abunny_stage1_discovery.analysis_ports import (
    CtaProductDetectorPort,
    HookClassifierPort,
    OverlayCutPointExtractorPort,
    TranscriptTimestampExtractorPort,
)
from abunny_stage1_discovery.adapters.fixture_adapters import FixtureAnalysisPipeline
from abunny_stage1_discovery.models import MediaDownloadJob, OverlayCutPoint, RawShortCandidate, TranscriptSegment


class TwelveLabsTranscriptMock(TranscriptTimestampExtractorPort):
    """Stub for vendor transcript + timestamp alignment."""

    def __init__(self, inner: FixtureAnalysisPipeline) -> None:
        self._inner = inner

    def extract_transcript_segments(
        self,
        candidate: RawShortCandidate,
        jobs: list[MediaDownloadJob],
    ) -> list[TranscriptSegment]:
        return self._inner.analyze(candidate, jobs).transcript


class GeminiHookClassifierMock(HookClassifierPort):
    def __init__(self, inner: FixtureAnalysisPipeline) -> None:
        self._inner = inner

    def classify_hook(
        self,
        candidate: RawShortCandidate,
        segments: list[TranscriptSegment],
    ) -> HookLabel:
        _ = segments
        label = self._inner.analyze(candidate, []).hook_label
        try:
            return HookLabel(label)
        except ValueError:
            return HookLabel.UNKNOWN


class GeminiOverlayCutsMock(OverlayCutPointExtractorPort):
    def __init__(self, inner: FixtureAnalysisPipeline) -> None:
        self._inner = inner

    def extract_cut_points(
        self,
        candidate: RawShortCandidate,
        segments: list[TranscriptSegment],
    ) -> list[OverlayCutPoint]:
        _ = segments
        return self._inner.analyze(candidate, []).overlay_cut_points


class GeminiCtaProductMock(CtaProductDetectorPort):
    def __init__(self, inner: FixtureAnalysisPipeline) -> None:
        self._inner = inner

    def detect_cta_and_product(
        self,
        candidate: RawShortCandidate,
        segments: list[TranscriptSegment],
    ) -> tuple[CtaKind, ProductIntegration]:
        _ = segments
        a = self._inner.analyze(candidate, [])
        try:
            cta = CtaKind(a.cta_kind)
        except ValueError:
            cta = CtaKind.NONE
        try:
            prod = ProductIntegration(a.product_integration)
        except ValueError:
            prod = ProductIntegration.NONE
        return cta, prod
