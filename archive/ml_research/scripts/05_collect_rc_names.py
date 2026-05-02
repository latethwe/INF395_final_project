import csv
from pathlib import Path

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "rc_names" / "raw_dropdawn.html"
OUTPUT_FILE = PROJECT_ROOT / "data" / "rc_names" / "almaty_rc_names.csv"


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input HTML not found: {INPUT_FILE}")

    html = INPUT_FILE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    names = [
        span.get_text(strip=True)
        for span in soup.select("span.cf-dropdown-item__label")
        if span.get_text(strip=True)
    ]
    names = sorted(set(names))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name"])
        for n in names:
            writer.writerow([n])

    print("TOTAL:", len(names))
    print("Saved to", OUTPUT_FILE)


if __name__ == "__main__":
    main()
