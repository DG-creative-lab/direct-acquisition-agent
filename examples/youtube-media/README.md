# Bundled YouTube comparison previews

These five rendered clips are copied byte for byte from merged YouTube PR #137,
source `2d4e60d4027217edada6c93153d02cc0aa17cc75`. The original passages are
read with OpenAI-generated speech: Marin for video editing and Cedar for the
audiobook. Scene artwork is AI-generated. Both takes within each context share
the same words and voice, with different delivery and pacing.

[Source definitions and provenance](https://github.com/DG-creative-lab/youtube-ad-agent/tree/2d4e60d4027217edada6c93153d02cc0aa17cc75/examples/viewer-media)
and [source authoring tool](https://github.com/DG-creative-lab/youtube-ad-agent/blob/2d4e60d4027217edada6c93153d02cc0aa17cc75/scripts/prepare_openai_samples.py).

The installed fixture passages and editing instruction match the source
[generation manifest](source-media-manifest.json). [provenance.json](provenance.json)
maps the original source v1 identifiers to this application's new v2 creative and
comparison identities. Regression tests check every passage, instruction, take,
filename and media hash against these frozen source records.

These are unbranded synthetic samples, not ElevenLabs output, customer campaign
evidence or a product-quality comparison. Existing historical approvals cannot
authorize the refreshed context. Keep earlier stores for historical inspection
and prepare a fresh YouTube conversation after upgrading.

Playback is offline. No API key, authoring integration or source application
history is imported. The comparison preview records no events; experiment
measurement follows under issue #133. Four additional ad-copy candidates, their
complete scripts and images are in [youtube-ad-samples](../youtube-ad-samples/README.md).
