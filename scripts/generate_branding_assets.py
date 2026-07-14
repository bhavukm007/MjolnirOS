"""Generate Windows branding rasters from the approved Mjolnir artwork."""

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "assets" / "branding"
APP_SIZES = (16, 24, 32, 48, 64, 128, 256)
TRAY_SIZES = (16, 24)


def square_artwork(source: Image.Image) -> Image.Image:
    """Preserve the complete portrait artwork inside a premium dark square."""
    edge = max(source.size)
    canvas = Image.new("RGBA", (edge, edge), (9, 11, 16, 255))
    canvas.alpha_composite(source, ((edge - source.width) // 2, (edge - source.height) // 2))
    return canvas


def write_sizes(source: Image.Image, prefix: str, sizes: tuple[int, ...]) -> None:
    for size in sizes:
        resized = source.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(BRANDING / f"{prefix}-{size}.png", optimize=True)


def main() -> None:
    icon_artwork = Image.open(BRANDING / "mjolnir-icon-original.jpg").convert("RGBA")
    app_source = square_artwork(icon_artwork)
    app_source.save(BRANDING / "mjolnir-app-source.png", optimize=True)
    app_source.save(BRANDING / "mjolnir-icon-source.png", optimize=True)
    write_sizes(app_source, "mjolnir-app", APP_SIZES)
    app_source.save(
        BRANDING / "mjolnir.ico",
        format="ICO",
        sizes=[(size, size) for size in APP_SIZES],
        bitmap_format="png",
    )

    tray = ImageOps.contain(app_source, (256, 256), Image.Resampling.LANCZOS)
    tray.save(BRANDING / "mjolnir-tray-source.png", optimize=True)
    write_sizes(tray, "mjolnir-tray", TRAY_SIZES)


if __name__ == "__main__":
    main()
