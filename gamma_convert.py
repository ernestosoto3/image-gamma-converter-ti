import math
import shlex
import struct
import subprocess
import tempfile
from pathlib import Path


SUPPORTED_OUTPUTS = {"png", "jpeg", "jpg", "bmp", "tiff"}


def parse_dragged_path(raw_input: str) -> Path:
    raw_input = raw_input.strip()
    if not raw_input:
        raise ValueError("No file path provided.")

    parts = shlex.split(raw_input)
    if not parts:
        raise ValueError("Invalid file path.")

    return Path(parts[0]).expanduser()


def run_sips_convert(input_path: Path, output_path: Path, output_format: str) -> None:
    fmt = output_format.lower()
    if fmt == "jpg":
        fmt = "jpeg"

    result = subprocess.run(
        ["sips", "-s", "format", fmt, str(input_path), "--out", str(output_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "sips conversion failed.")


def apply_gamma_to_bmp(input_bmp: Path, output_bmp: Path, gamma: float) -> None:
    if gamma <= 0:
        raise ValueError("Gamma must be greater than 0.")

    data = input_bmp.read_bytes()

    if len(data) < 54:
        raise ValueError("Invalid BMP file.")

    if data[0:2] != b"BM":
        raise ValueError("Not a BMP file.")

    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    dib_header_size = struct.unpack_from("<I", data, 14)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bits_per_pixel = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]

    if dib_header_size < 40:
        raise ValueError("Unsupported BMP header.")
    if compression != 0:
        raise ValueError("Compressed BMP not supported.")
    if bits_per_pixel not in (24, 32):
        raise ValueError(f"Only 24-bit and 32-bit BMP supported, got {bits_per_pixel}.")

    top_down = height < 0
    abs_height = abs(height)
    bytes_per_pixel = bits_per_pixel // 8
    row_size = ((bits_per_pixel * width + 31) // 32) * 4

    out = bytearray(data)

    # Gamma table:
    # gamma < 1.0 => lighter
    # gamma > 1.0 => darker
    inv = gamma
    table = [min(255, max(0, int((i / 255.0) ** inv * 255.0 + 0.5))) for i in range(256)]

    for row in range(abs_height):
        bmp_row = row if top_down else (abs_height - 1 - row)
        row_start = pixel_offset + bmp_row * row_size

        for col in range(width):
            px = row_start + col * bytes_per_pixel
            b = out[px]
            g = out[px + 1]
            r = out[px + 2]

            out[px] = table[b]
            out[px + 1] = table[g]
            out[px + 2] = table[r]
            # alpha channel untouched if 32-bit

    output_bmp.write_bytes(out)


def gamma_convert_image(input_file: Path, gamma: float, output_format: str | None = None) -> Path:
    if not input_file.exists():
        raise FileNotFoundError(f"File not found: {input_file}")

    if gamma <= 0:
        raise ValueError("Gamma must be greater than 0.")

    original_ext = input_file.suffix.lower().lstrip(".")
    if original_ext == "jpg":
        original_ext = "jpeg"

    if output_format is None:
        output_format = original_ext or "jpeg"

    output_format = output_format.lower()
    if output_format == "jpg":
        output_format = "jpeg"

    if output_format not in SUPPORTED_OUTPUTS:
        raise ValueError(f"Unsupported output format: {output_format}")

    output_file = input_file.with_name(f"{input_file.stem}_gamma_{str(gamma).replace('.', '_')}.{output_format}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        temp_bmp_in = tmpdir / "input.bmp"
        temp_bmp_out = tmpdir / "output.bmp"

        run_sips_convert(input_file, temp_bmp_in, "bmp")
        apply_gamma_to_bmp(temp_bmp_in, temp_bmp_out, gamma)
        run_sips_convert(temp_bmp_out, output_file, output_format)

    return output_file


def show_gamma_help() -> None:
    print("\nGamma guide:")
    print("  0.5  -> much lighter")
    print("  0.8  -> slightly lighter")
    print("  1.0  -> no change")
    print("  1.4  -> slightly darker")
    print("  2.1  -> noticeably darker")
    print("  2.5  -> much darker")
    print("\nRule:")
    print("  gamma < 1.0 = lighter")
    print("  gamma = 1.0 = no change")
    print("  gamma > 1.0 = darker\n")


if __name__ == "__main__":
    try:
        print("=== Gamma Image Converter (macOS, no pip installs) ===")
        show_gamma_help()

        raw_path = input("Drag your image here, then press Enter:\n")
        input_path = parse_dragged_path(raw_path)

        gamma_str = input("Enter gamma value (example: 0.8, 1.0, 2.1): ").strip()
        gamma_value = float(gamma_str)

        output_format = input(
            f"Enter output format [png/jpeg/bmp/tiff] or press Enter to keep .{input_path.suffix.lstrip('.')}:\n"
        ).strip()

        if not output_format:
            output_format = None

        new_file = gamma_convert_image(input_path, gamma_value, output_format)

        print(f"\nDone.")
        print(f"Gamma used: {gamma_value}")
        print(f"Saved file:\n{new_file}")

    except Exception as e:
        print(f"\nError: {e}")