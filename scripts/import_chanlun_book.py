"""Import the pinned, attributed 108-course archive into same-origin reading assets.

Usage: python scripts/import_chanlun_book.py PATH_TO_CHECKOUT
The checkout is read as data only. No archive code is executed.
"""
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "d2a87d5bd9c84baac2918edca668b9f82a20be52"
REPOSITORY = "https://github.com/stockServ/chzhshch-108-plus"
VERSION = COMMIT[:12]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(checkout):
    checkout = Path(checkout).resolve()
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != COMMIT:
        raise ValueError("Archive commit does not match the reviewed source")
    entries = {}
    for path in (checkout / "108").glob("*.md"):
        match = re.search(r"-(\d{3})\.md$", path.name)
        if match and 1 <= int(match[1]) <= 108:
            number = int(match[1])
            if number in entries:
                raise ValueError(f"Duplicate course {number}")
            entries[number] = path
    if set(entries) != set(range(1, 109)):
        raise ValueError("Archive must contain exactly courses 1-108")

    permissions = []
    for number, phrase in [(8, "各位如果转载，请注明出处"), (17, "可以，但一定要顺便推广一下本博客")]:
        text = entries[number].read_text(encoding="utf-8")
        matches = [block.strip() for block in text.split("```") if "UID:[1215172700] 昵称：缠中说禅" in block and phrase in block]
        if len(matches) != 1:
            raise ValueError("Expected attributed author permission record not found")
        permissions.append({"course": number, "archiveFile": entries[number].name, "record": matches[0]})

    destination = ROOT / "frontend/public/reading-assets/chanlun" / VERSION
    destination.mkdir(parents=True, exist_ok=True)
    catalog, assets = [], {}
    image_count = 0
    for number, path in sorted(entries.items()):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        body, separator, _comments = text.partition("**本文评论")
        if not separator:
            raise ValueError(f"Comment boundary missing in course {number}")
        heading = re.search(r"^#\s*\d+\s*-\s*(.+)$", body, re.M)
        stamp = re.search(r"日期：[（(]([^）)]+)[）)]\s*分类：\[([^\]]+)\]", body)
        if not heading or not stamp:
            raise ValueError(f"Course metadata missing: {number}")
        body = body[stamp.end():].strip()
        blocks = []
        for index, piece in enumerate(re.split(r"!\[([^\]]*)\]\(([^)]+)\)", body)):
            # split returns text, alt, image path, text, ...
            if index % 3 == 1:
                continue
            if index % 3 == 2:
                image = (path.parent / piece).resolve()
                if not image.is_relative_to((checkout / "108/pic").resolve()) or not image.is_file():
                    raise ValueError(f"Unexpected or missing image: {piece}")
                filename = digest(image.read_bytes())[:16] + image.suffix.lower()
                target = destination / "images" / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(image, target)
                assets[f"images/{filename}"] = digest(target.read_bytes())
                blocks.append({"type": "image", "src": f"/reading-assets/chanlun/{VERSION}/images/{filename}", "alt": f"第{number}课原文配图"})
                image_count += 1
            else:
                for paragraph in re.split(r"\n\s*\n", piece):
                    paragraph = html.unescape(paragraph.strip())
                    if paragraph:
                        blocks.append({"type": "text", "text": paragraph})
        word_count = sum(len(block.get("text", "")) for block in blocks)
        if word_count < 100:
            raise ValueError(f"Unexpectedly short course {number}")
        article_id = re.search(r"-(486e105c[0-9a-z]+)-", path.name)[1]
        source_url = f"https://blog.sina.com.cn/s/blog_{article_id}.html"
        title = heading[1].strip()
        filename = f"chapter-{number:03d}.json"
        record = {"number": number, "title": title, "author": "缠中说禅", "publishedAt": stamp[1],
                  "sourceUrl": source_url, "blocks": blocks, "textLength": word_count}
        write_json(destination / filename, record)
        assets[filename] = digest((destination / filename).read_bytes())
        catalog.append({"number": number, "title": title, "sourceUrl": source_url,
                        "contentPath": f"/reading-assets/chanlun/{VERSION}/{filename}", "textLength": word_count,
                        "archiveFile": path.name, "archiveSha256": digest(raw)})

    shutil.copyfile(checkout / "LICENSE", destination / "LICENSE.txt")
    notice = "原文作者：缠中说禅。原始发表：缠中说禅新浪博客 https://blog.sina.com.cn/chzhshch\n" \
             "根据第8、17课作者回复中的转载许可整理，保留署名、出处并推广作者原博客。\n" \
             "档案整理：stockServ/chzhshch-108-plus（MIT）；原文版权归原作者所有。\n" \
             "本版仅收录108课正文及整理档案中的配图，不混入网友评论、疑似小号回复或本站解读。\n"
    (destination / "NOTICE.txt").write_text(notice, encoding="utf-8")
    write_json(destination / "provenance.json", {"repository": REPOSITORY, "commit": COMMIT,
               "authorPermissions": permissions, "assetSha256": assets, "notice": notice})
    write_json(ROOT / "frontend/src/content/chanlunChapters.json", {
        "author": "缠中说禅", "version": VERSION, "repository": REPOSITORY, "sourceCommit": COMMIT,
        "provenancePath": f"/reading-assets/chanlun/{VERSION}/provenance.json", "chapters": catalog})
    print(f"Imported {len(catalog)} complete courses, {image_count} image references, {sum(c['textLength'] for c in catalog)} text characters")


if __name__ == "__main__":
    main(sys.argv[1])
