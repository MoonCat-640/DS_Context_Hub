"""将高清透明 PNG 导出为 Windows 多尺寸 ICO。仅在更换图标时需要 Pillow。"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def main():
    with Image.open(ASSETS / "ds-context-hub.png") as master:
        if master.width != master.height or master.width < max(SIZES) or "A" not in master.getbands():
            raise ValueError("图标母版需要带透明通道的正方形 PNG，边长至少 256 像素")
        # 每一档都从母版采样，Windows 可按桌面缩放率选用最接近的尺寸。
        master.save(ASSETS / "ds-context-hub.ico", format="ICO", sizes=[(size, size) for size in SIZES])


if __name__ == "__main__":
    main()
