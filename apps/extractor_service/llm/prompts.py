SCHEMA_TR = """Sadece GEÇERLİ JSON üret. Bulunamayan alanları null yap. ISO tarih (YYYY-MM-DD).
Şema:
{
 "Masraf": {"Kod": null, "BaslangicTarihi": "", "BitisTarihi": "", "Aciklama": "", "Bolum": null, "Hash": null},
 "MasrafAlt": [{"Kod": null, "MasrafTarihi": "", "MasrafTuru": "", "Butce": null, "Tedarikci": "", "Miktar": 1, "Birim": "", "BirimMasrafTutari": 0.0, "KDVOrani": 0, "ToplamMasrafTutari": 0.0, "Aciklama": ""}],
 "Dosya": [{"Kod": null, "Adi": null, "OrjinalAdi": "", "Hash": null, "MimeType": "", "Size": null, "Md5": null, "EklenmeTarihi": null}]
}"""

def text_user_prompt(description: str, pages: list[str], tables: str|None=None, email: str|None=None) -> str:
    parts = []
    if description: parts += [f"Açıklama:\n{description}\n"]
    if email: parts += [f"E-posta:\n{email}\n"]
    for i, t in enumerate(pages, 1):
        parts += [f"# Sayfa {i}\n{t}\n"]
    if tables: parts += [f"# Tablolar\n{tables}\n"]
    parts += ["Yukarıdaki içeriğe göre şemaya uygun JSON üret."]
    return "\n".join(parts)
