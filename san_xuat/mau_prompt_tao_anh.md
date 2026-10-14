You are designing the images for a vertical 9:16 explainer video (TikTok / Reels / Shorts) about self-drive car rental in Vietnam. A separate program will turn your images into an animated video: it erases the "animated elements" you list from each image, then makes them slide in or pop in one by one exactly when the voice-over says the matching words. So for EVERY image you must also return a JSON description of its animated elements.

# Video: {{TIEU_DE}}

# Visual style (identical for every image)
- Flat vector infographic illustration, clean and friendly, 1080x1920 px, portrait 9:16.
- Background: plain, soft light-blue to white vertical gradient (#EEF4FF -> #FFFFFF), or a plain dark navy gradient (#0F172A -> #1E293B) for "problem / worry" scenes. No busy patterns, no photos, no texture.
- Colors: brand blue #155ECF, navy text #0F172A, orange highlight #FF8800, red warning #E53935, green OK #22A05A, white rounded cards with a very soft shadow.
- Characters: simple friendly Vietnamese cartoon people, same character design in every scene (car owner: short black hair, blue shirt; customer: orange or green shirt).
- All on-image text is in Vietnamese with correct diacritics, bold sans-serif, large and short (max ~8 words per element). Write every text EXACTLY as given below, letter by letter.

# Layout rules (so the program can find and animate the elements)
1. Title zone: top 22% of the image. The scene title sits here, centered. The title is STATIC (never listed in JSON).
2. Animated elements (cards, list rows, steps, badges, icons, buttons) sit directly on the plain background, each clearly separated from its neighbours by at least 24 px of empty background. They must NOT overlap each other, the title, or the characters.
3. A list = one element per row (or per card). Do not merge several list items into one card.
4. Keep the bottom 15% of the image free of important content (subtitles go there).
5. Static parts (background, main character, large illustration) are simply not listed in the JSON.

# JSON to return after EACH image
Right after generating an image, reply with one fenced ```json block for that scene:

```json
{
  "so": 3,
  "anh": "03_chuyen_y.png",
  "tam_zoom": [0.5, 0.55],
  "khoi": [
    {
      "chu": "5 việc cần làm trước khi giao xe",
      "mo_ta": "orange rounded button under the title",
      "vung": [0.11, 0.26, 0.89, 0.32],
      "hien_khi": "Đây là 5 việc",
      "hieu_ung": "truot"
    },
    {
      "chu": "",
      "mo_ta": "green shield with a white check mark",
      "vung": [0.72, 0.36, 0.91, 0.50],
      "hien_khi": "kiểm soát được",
      "hieu_ung": "bat"
    }
  ]
}
```

Field rules:
- "so": the scene number. "anh": the file name the user should save the image as (given per scene below).
- "khoi": the animated elements, listed in the ORDER they should appear.
- "chu": the exact Vietnamese text printed on that element, as it appears in the image ("" if the element has no text, e.g. an icon).
- "mo_ta": a few English words describing the element (shape, color).
- "vung": the element's bounding box as fractions of the image [left, top, right, bottom], 0 = top-left corner, 1 = bottom-right corner. Cover the whole element (card background, icon, check mark) with a small margin. An estimate is fine; the program refines it.
- "hien_khi": 2 to 6 CONSECUTIVE words copied VERBATIM from that scene's voice-over below, spoken at the moment the element should appear.
- "hieu_ung": one of "truot" (slide up: cards, rows, text, steps), "bat" (pop in: icons, stamps, badges, question marks), "mo_dan" (fade in: a larger picture), "nhip" (pop in then keep pulsing: the final call-to-action button only).
- "tam_zoom" (optional): [x, y] fraction of the point the camera should slowly zoom towards.
- Scenes with several frames ("N ảnh" below): create N separate images, return one JSON per image with "khoi": [] (frames are cut automatically).
- The cover image: return its JSON with "so": 0 and "khoi": [].

When a scene below already lists its animated elements as a JSON skeleton, draw exactly those elements (same text, same order) and return that skeleton with "vung" filled in; keep "chu", "hien_khi" and "hieu_ung" unchanged.

# Final deliverable (after ALL images are generated)
Return ONE summary file named `hieu_ung.json` that combines everything: {"canh": [ ...every scene object above, including the cover "so": 0... ]}.
- If you can create files, attach it as a downloadable `hieu_ung.json` file.
- Otherwise output it as a single ```json code block with nothing else inside, so the user can copy it into hieu_ung.json.
- Double-check before sending: every scene is present, every "hien_khi" is copied verbatim from that scene's voice-over, every "vung" is inside [0, 1], and the JSON is valid (no comments, no trailing commas).

# Scenes
{{CANH}}
