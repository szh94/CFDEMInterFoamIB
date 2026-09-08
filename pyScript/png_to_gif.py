#!/usr/bin/env python3
"""Convert numbered PNG frame sequences in ani/ to GIF files."""

import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("错误：缺少 Pillow，请先执行：python3 -m pip install Pillow")


FRAME_PATTERN = re.compile(r"^(?P<name>.+)\.(?P<number>\d+)\.png$", re.IGNORECASE)


def main() -> int:
    ani_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "ani"
    if not ani_dir.is_dir():
        print(f"错误：动画目录不存在：{ani_dir}", file=sys.stderr)
        return 1

    sequences = defaultdict(list)
    for path in ani_dir.iterdir():
        match = FRAME_PATTERN.match(path.name)
        if path.is_file() and match:
            sequences[match.group("name")].append((int(match.group("number")), path))

    if not sequences:
        print(f"未识别到 PNG 序列：{ani_dir}", file=sys.stderr)
        return 1

    for name in sorted(sequences):
        frame_paths = [path for _, path in sorted(sequences[name])]
        output_path = ani_dir / f"{name}.gif"
        print(f"识别到动画：{name}")
        print(f"帧数：{len(frame_paths)}，输出：{output_path}")

        frames = []
        try:
            for path in frame_paths:
                with Image.open(path) as image:
                    frames.append(image.convert("RGBA"))

            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
                disposal=2,
            )
        finally:
            for frame in frames:
                frame.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
