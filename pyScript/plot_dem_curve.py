#!/usr/bin/env python3
"""Draw DEM particle curves from the LIGGGHTS dump files in DEM/post.

The dumps count steps, not seconds: each frame carries an ``ITEM: TIMESTEP``
line, and the physical time is that step times the DEM time step the deck
defines in ``variable timestep equal ...``.  So the time axis is computed from
the two, never assumed.

The figure goes to ``<case>/results/``.
"""

import re
import sys
from pathlib import Path

try:
    import matplotlib

    # No display when run from a terminal or over ssh; pick the backend before
    # pyplot is imported, since importing it already fixes one.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit("错误：缺少 matplotlib，请先执行：sudo apt install python3-matplotlib")


#: ``variable timestep equal 0.00001``: the one line that turns a dump's step
#: count into seconds.
_TIMESTEP = re.compile(r"^\s*variable\s+timestep\s+equal\s+(?P<value>[0-9.eE+\-]+)")

#: ``dump3000.liggghts``; the number is the step that frame was written at.
_DUMP = re.compile(r"^dump(?P<step>\d+)\.liggghts$", re.IGNORECASE)


def read_dem_timestep(deck: Path):
    """The DEM time step from the LIGGGHTS input, or ``None`` if it has none."""
    if not deck.is_file():
        return None
    for line in deck.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _TIMESTEP.match(line)
        if match:
            try:
                return float(match.group("value"))
            except ValueError:
                return None
    return None


def find_dumps(post_dir: Path):
    """``[(step, path)]`` in step order; anything else in the directory is ignored."""
    out = []
    for path in post_dir.iterdir():
        match = _DUMP.match(path.name)
        if path.is_file() and match:
            out.append((int(match.group("step")), path))
    return sorted(out)


def parse_dump(path: Path):
    """One ``{column: text}`` per atom, with the columns read off the header.

    A custom dump names its own fields, and the list is whatever the deck asked
    for -- so the names come from ``ITEM: ATOMS`` rather than from fixed
    positions, and a case that dumps a different set still reads.
    """
    columns = None
    rows = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("ITEM: ATOMS"):
                columns = line.split()[2:]
                continue
            if columns is None:
                continue
            fields = line.split()
            # A short line is a truncated last write, not an atom.
            if len(fields) < len(columns):
                continue
            rows.append(dict(zip(columns, fields)))
    return rows


def series_by_particle(dumps, dt, column):
    """``{particle id: (times, values)}`` for one dump column, in step order."""
    series = {}
    for step, path in dumps:
        time = step * dt
        for atom in parse_dump(path):
            try:
                pid = int(atom["id"])
                value = float(atom[column])
            except (KeyError, ValueError):
                continue
            times, values = series.setdefault(pid, ([], []))
            times.append(time)
            values.append(value)
    return series


def draw(series, out_path: Path, case_name: str, title: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=160)
    for pid in sorted(series):
        times, values = series[pid]
        ax.plot(
            times, values, marker="o", markersize=2.6, linewidth=1.3,
            label=f"particle {pid}",
        )
    ax.set_xlabel("t (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title} — {case_name}")
    ax.grid(True, alpha=0.3)
    # One curve needs no key; the title already says what it is.
    if len(series) > 1:
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：plot_dem_curve.py <算例目录>", file=sys.stderr)
        return 1

    case_dir = Path(sys.argv[1]).resolve()
    post_dir = case_dir / "DEM" / "post"
    if not post_dir.is_dir():
        print(f"错误：找不到 DEM 数据目录：{post_dir}", file=sys.stderr)
        return 1

    dumps = find_dumps(post_dir)
    if not dumps:
        print(f"错误：{post_dir} 里没有 dump*.liggghts", file=sys.stderr)
        return 1

    deck = case_dir / "DEM" / "in.liggghts_run"
    dt = read_dem_timestep(deck)
    if dt is None:
        print(f"错误：{deck} 里没有 variable timestep equal ...，无法换算时间轴", file=sys.stderr)
        return 1

    series = series_by_particle(dumps, dt, "vz")
    if not series:
        print("错误：dump 里没有可用的 id / vz 列", file=sys.stderr)
        return 1

    results = case_dir / "results"
    results.mkdir(exist_ok=True)

    first, last = dumps[0][0], dumps[-1][0]
    out_path = results / "vz_vs_time.png"
    draw(series, out_path, case_dir.name, "Particle z velocity", "v_z (m/s)")

    print(f"读取 {len(dumps)} 帧 dump（步 {first}..{last}），DEM 时间步 {dt:g} s")
    print(f"时间范围：0 .. {last * dt:g} s")
    print(f"粒子数：{len(series)}，数据点：{sum(len(v[0]) for v in series.values())}")
    print(f"已输出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
