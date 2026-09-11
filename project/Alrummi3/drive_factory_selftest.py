"""Fast dependency-free (apart from Pillow) safety checks for drive_factory.py.

Run:
    python drive_factory_selftest.py

No network, Google credentials, or OpenAI credentials are used.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from PIL import Image, ImageDraw

from drive_factory import (
    Box,
    FactoryConfig,
    candidate_image,
    create_job,
    result_available,
    validate_result,
)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS  {name}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="alrummi3_factory_test_") as temp:
        root = Path(temp) / "Alrummi3_AI_Factory"
        config = FactoryConfig(
            root=root,
            max_outside_change_ratio=0.0,
            pixel_difference_threshold=0,
        )

        source = Image.new("RGBA", (64, 32), (30, 40, 50, 255))
        draw = ImageDraw.Draw(source)
        draw.rectangle((10, 8, 29, 19), fill=(180, 180, 180, 255))
        edit_box = Box(10, 8, 30, 20)

        job = create_job(
            config,
            source,
            texture_name="cockpit_test_ID_HQ",
            metadata={"format": "BC3", "owner": "cockpit LSP"},
            editable_regions=[edit_box],
            instructions="Replace the grey test label only.",
        )
        check("job writes manifest and readiness marker", job.manifest_path.is_file() and (job.inbox_dir / ".ready").is_file())
        check("job preserves exact source dimensions", job.width == 64 and job.height == 32)

        valid = source.copy()
        vdraw = ImageDraw.Draw(valid)
        vdraw.rectangle((12, 10, 27, 17), fill=(255, 255, 255, 255))
        valid.save(job.result_path)
        check("completed result becomes visible", result_available(job))
        good_report = validate_result(config, job)
        check("region-only edit is accepted", good_report.ok)
        detached = candidate_image(job, config)
        check("validated candidate can be loaded", detached.size == source.size and detached.mode == "RGBA")
        detached.close()

        bad = valid.copy()
        bad.putpixel((1, 1), (255, 0, 0, 255))
        bad.save(job.result_path)
        bad_report = validate_result(config, job)
        check("unapproved outside-region edit is rejected", not bad_report.ok and any("outside" in e.lower() for e in bad_report.errors))

        wrong = Image.new("RGBA", (63, 32), (0, 0, 0, 255))
        wrong.save(job.result_path)
        wrong_report = validate_result(config, job)
        check("wrong dimensions are rejected", not wrong_report.ok and any("dimensions" in e.lower() for e in wrong_report.errors))

        print("\nDrive factory self-test: 7/7 passed")


if __name__ == "__main__":
    main()
