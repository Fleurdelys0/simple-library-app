# 📚 Kütüphane Yönetim Sistemi

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-green?style=for-the-badge&logo=fastapi)
![Tests](https://img.shields.io/badge/tests-passing-success?style=for-the-badge&logo=pytest)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)

Bu proje, basit bir komut satırı uygulamasından başlayarak, harici bir API ile veri zenginleştirmesi yapan ve son olarak tüm bu mantığı bir web servisi olarak sunan kapsamlı bir kütüphane yönetim sistemidir.

---

## 🌟 Genel Bakış

Proje, modern Python geliştirme pratiklerini sergilemek amacıyla üç ana aşamada geliştirilmiştir:

1.  **OOP Konsol Uygulaması:** Nesne Yönelimli Programlama (OOP) prensipleriyle yapılandırılmış, terminal üzerinden çalışan bir kütüphane.
2.  **Harici API Entegrasyonu:** [Open Library API](https://openlibrary.org/developers/api)'sini kullanarak kitap bilgilerini ISBN ile otomatik olarak getirme.
3.  **FastAPI Web Servisi:** Kütüphane mantığını, RESTful endpoint'ler üzerinden erişilebilir bir web API'sine dönüştürme.

## ✨ Özellikler

- **Komut Satırı Arayüzü (CLI):** `Typer` ve `Rich` ile geliştirilmiş, kullanıcı dostu bir terminal arayüzü.
- **Veri Kalıcılığı:** Kitap verileri `SQLite` veritabanında güvenilir bir şekilde saklanır.
- **Otomatik Veri Zenginleştirme:** ISBN numarası ile Open Library'den kitap başlığı ve yazar bilgilerini otomatik çeker.
- **RESTful API:** `FastAPI` ile oluşturulmuş, tam özellikli ve belgelenmiş bir web servisi.
- **Etkileşimli Dokümantasyon:** FastAPI'nin sunduğu Swagger UI (`/docs`) ve Redoc (`/redoc`) ile otomatik oluşturulan API dokümanları.
- **Gelişmiş Özellikler:** Arama, istatistik, veri import/export (JSON/CSV) ve daha fazlası.
- **Kapsamlı Testler:** `pytest` ile yazılmış birim ve entegrasyon testleri.

## 🛠️ Teknoloji Yığını

![SQLite](https://img.shields.io/badge/SQLite-blue?style=flat-square&logo=sqlite&logoColor=white)
![HTTPX](https://img.shields.io/badge/HTTPX-purple?style=flat-square)
![Uvicorn](https://img.shields.io/badge/Uvicorn-green?style=flat-square)
![Pytest](https://img.shields.io/badge/Pytest-blue?style=flat-square)
![Typer](https://img.shields.io/badge/Typer-black?style=flat-square)
![Rich](https://img.shields.io/badge/Rich-purple?style=flat-square)

---

## 🚀 Kurulum

Projeyi yerel makinenizde çalıştırmak için aşağıdaki adımları izleyin:

1.  **Depoyu Klonlayın:**
    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

2.  **(Önerilir) Sanal Ortam Oluşturun:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate    # Windows
    ```

3.  **Bağımlılıkları Yükleyin:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### 🖥️ Komut Satırı Arayüzü (CLI)

Etkileşimli menüyü başlatmak için:

```bash
python main.py
```

Menü üzerinden kitap ekleyebilir, silebilir, listeleyebilir ve arayabilirsiniz.

### 🌐 API Sunucusu

FastAPI sunucusunu başlatmak için:

```bash
uvicorn api:app --reload
```

Sunucu varsayılan olarak `http://127.0.0.1:8000` adresinde çalışacaktır.

- **Swagger UI (Etkileşimli Test):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc (Alternatif Dokümantasyon):** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 📖 API Endpoint'leri

Aşağıda temel API endpoint'lerinin bir özeti bulunmaktadır. Tüm endpoint'leri ve detaylarını `/docs` adresinde bulabilirsiniz.

| Metod  | Endpoint            | Açıklama                                       | Örnek Body / Parametre                |
| :----- | :------------------ | :--------------------------------------------- | :------------------------------------ |
| `GET`  | `/books`            | Kütüphanedeki tüm kitapları listeler.          | -                                     |
| `POST` | `/books`            | ISBN ile yeni bir kitap ekler.                 | `{"isbn": "9780321765723"}`           |
| `GET`  | `/books/{isbn}`     | Belirtilen ISBN'e sahip tek bir kitabı getirir.| `isbn`: `9780321765723`                |
| `PUT`  | `/books/{isbn}`     | Bir kitabın bilgilerini günceller.             | `{"title": "Yeni Başlık"}`            |
| `DELETE`| `/books/{isbn}`    | Belirtilen ISBN'e sahip kitabı siler.          | `isbn`: `9780321765723`                |
| `GET`  | `/stats`            | Kütüphane istatistiklerini döndürür.           | -                                     |

*Not: `POST`, `PUT`, `DELETE` işlemleri için `X-API-Key` başlığında bir API anahtarı gönderilmesi gerekmektedir. Varsayılan anahtar `config.py` dosyasında tanımlıdır.*

## ✅ Testler

Projenin tüm testlerini çalıştırmak için:

```bash
python -m pytest
```

Testler, veritabanı işlemlerini, CLI komutlarını ve API endpoint'lerini kapsamaktadır.
