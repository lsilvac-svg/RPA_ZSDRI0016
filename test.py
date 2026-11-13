from pathlib import Path

from PIL import Image, ImageSequence

entrada = Path(__file__).parent / "20261112161306119.tif"
salida = entrada.with_suffix(".pdf")

with Image.open(entrada) as img:
    # Un TIFF puede tener varias páginas: se convierten todas
    paginas = [pagina.convert("RGB") for pagina in ImageSequence.Iterator(img)]

paginas[0].save(salida, "PDF", save_all=True, append_images=paginas[1:], resolution=200)
print(f"PDF generado: {salida} ({len(paginas)} página(s))")
