"""Analysis adapters (TwelveLabs, Gemini, etc.) as ports with fixture/mock impls."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from abunny_stage1_discovery.models import (
    AnalyzedCandidate,
    MediaDownloadJob,
    OverlayCutPoint,
    RawShortCandidate,
    TranscriptSegment,
)
from abunny_stage1_discovery.analysis_enums import CtaKind, HookLabel, ProductIntegration


@runtime_checkable
class TranscriptTimestampExtractorPort(Protocol):
    def extract_transcript_segments(
        self,
        candidate: RawShortCandidate,
        jobs: list[MediaDownloadJob],
    ) -> list[TranscriptSegment]:
        ...


@runtime_checkable
class HookClassifierPort(Protocol):
    def classify_hook(self, candidate: RawShortCandidate, segments: list[TranscriptSegment]) -> HookLabel:
        ...


@runtime_checkable
class OverlayCutPointExtractorPort(Protocol):
    def extract_cut_points(
        self,
        candidate: RawShortCandidate,
        segments: list[TranscriptSegment],
    ) -> list[OverlayCutPoint]:
        ...


@runtime_checkable
class CtaProductDetectorPort(Protocol):
    def detect_cta_and_product(
        self,
        candidate: RawShortCandidate,
        segments: list[TranscriptSegment],
    ) -> tuple[CtaKind, ProductIntegration]:
        ...


@runtime_checkable
class AnalysisPipelinePort(Protocol):
    """Optional facade over the four analysis steps (mocked as one unit in dry-run)."""

    def analyze(self, candidate: RawShortCandidate, jobs: list[MediaDownloadJob]) -> AnalyzedCandidate:
        ...
