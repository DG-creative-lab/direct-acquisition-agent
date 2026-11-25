# YouTube voice studies: sample ads

These four unbranded sample ads are copied unchanged from the merged YouTube
source at `2d4e60d4027217edada6c93153d02cc0aa17cc75`:
[source PR #137](https://github.com/DG-creative-lab/youtube-ad-agent/pull/137).

| Context | Variation | Preview | Creative idea |
| --- | --- | --- | --- |
| Video editing | A | [Play](editing-a.mp4) | The cut is ready. Is the voice? |
| Video editing | B | [Play](editing-b.mp4) | Same scene. Different feeling. |
| Audiobook | A | [Play](audiobook-a.mp4) | Make the first line worth following. |
| Audiobook | B | [Play](audiobook-b.mp4) | A whole story starts with one voice. |

[copy.json](copy.json) records hooks, primary text, complete spoken scripts, calls
to action and delivery directions. Adjacent VTT files carry the scripts.
[image-prompts.json](image-prompts.json) records the original built-in imagegen
prompts. OpenAI generated the speech with Marin and Cedar; FFmpeg rendered the
1280 by 720 videos with a separate typography layer. Each video discloses its
AI-generated voice and imagery. No real product performance is asserted.

[checksums.json](checksums.json) maps all 15 copied media/image/caption assets to
their destination paths and preserves the exact source hashes and sizes. The
five installed comparison recordings live separately in
[youtube-media](../youtube-media/README.md).

These ads are creative candidates for later selection in the application. They
are not substituted for comparison previews, admitted to the comparison media
allowlist or presented as a controlled experiment. Each ad has its own script;
the comparison takes retain identical wording within their context.

The destination app plays existing comparison files offline. This import adds
no OpenAI client, API key, inference call, hosted publication or advertising
execution. Regenerate or revise media in the source authoring workflow, then
update files, fixture text, provenance and identities together for fresh review.
