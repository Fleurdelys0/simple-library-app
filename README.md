# 📚 AI Destekli Kütüphane Yönetim Sistemi

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-green?style=for-the-badge&logo=fastapi)
![Docker](https://img.shields.io/badge/Docker-blue?style=for-the-badge&logo=docker)
![Tests](https://img.shields.io/badge/tests-passing-success?style=for-the-badge&logo=pytest)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)

Bu proje, basit bir komut satırı uygulamasından evrilerek; **Google Books** ve **Hugging Face** gibi modern API'lerle entegre, AI destekli özellikler sunan, **Redis** ile önbelleğe alınmış, **Docker** üzerinde çalışan ve zengin bir web arayüzüne sahip tam yığın (full-stack) bir kütüphane yönetim sistemidir.

---

## 🌟 Genel Bakış

Proje, modern yazılım geliştirme pratiklerini sergilemek amacıyla kapsamlı bir şekilde yeniden yapılandırılmış ve geliştirilmiştir. Artık sadece bir CLI uygulaması değil, aynı zamanda aşağıdaki katmanları içeren bütünleşik bir sistemdir:

1.  **Gelişmiş CLI:** `Rich` ve `Typer` ile oluşturulmuş, menü tabanlı, kullanıcı dostu bir komut satırı arayüzü.
2.  **Akıllı Veri Entegrasyonu:** Kitap bilgilerini **Google Books API**'si üzerinden zenginleştirir ve benzer kitap önerileri sunar.
3.  **AI Destekli Özellikler:** **Hugging Face API**'si ile kitap açıklamalarından otomatik özetler oluşturur ve duygu analizi yapar.
4.  **Yüksek Performanslı Web Servisi:** **FastAPI** ile geliştirilmiş, **Redis** ile önbelleğe alınmış, asenkron ve ölçeklenebilir bir RESTful API.
5.  **Etkileşimli Web Arayüzü:** Vanilya JavaScript ile oluşturulmuş, modern, dinamik ve görsel olarak zengin bir tek sayfa uygulaması (SPA).
6.  **Container Desteği:** **Docker** ve `docker-compose` ile kolay kurulum ve dağıtım imkanı.

## ✨ Öne Çıkan Özellikler

- **Etkileşimli Web Arayüzü:**
    - Açık/Koyu tema desteği ve modern tasarım.
    - Kitapları arama, filtreleme ve etiketleme.
    - Kitap detaylarını (AI özetleri dahil) gösteren dinamik modal pencereler.
    - `Chart.js` ile görselleştirilmiş kütüphane istatistikleri.
    - `Toastify` ile kullanıcı bildirimleri ve `SweetAlert2` ile şık diyaloglar.
- **AI Destekli İşlemler:**
    - Kitap açıklamalarından otomatik olarak Türkçe özetler oluşturma.
    - Kitap incelemeleri için duygu analizi yapma.
- **Gelişmiş Arka Uç:**
    - **Google Books Entegrasyonu:** ISBN ile kitap eklerken sayfa sayısı, kategoriler, yayın tarihi gibi zengin verilerle donatma.
    - **Redis Önbellekleme:** Sık erişilen verileri (API yanıtları, kapak resimleri) önbelleğe alarak yüksek performans sağlama.
    - **Tam Kapsamlı API:** Kitap yönetimi, etiketleme, inceleme/puanlama, gelişmiş arama, haber akışı ve daha fazlası için RESTful endpoint'ler.
- **Veri Yönetimi:**
    - Verilerin `SQLite` veritabanında kalıcı olarak saklanması.
    - Kütüphaneyi JSON veya CSV formatında içe/dışa aktarma.
- **Kullanıcı Dostu CLI:**
    - `Rich` kütüphanesi ile zenginleştirilmiş menü tabanlı arayüz.
    - Web sunucusunu başlatma, toplu kitap ekleme ve yapılandırma yönetimi için komutlar.
- **Kolay Kurulum:** `docker-compose` ile tek komutla tüm sistemi (uygulama + Redis) ayağa kaldırma.

## 🛠️ Teknoloji Yığını

![FastAPI](https://img.shields.io/badge/FastAPI-green?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-blue?style=flat-square&logo=python)
![Docker](https://img.shields.io/badge/Docker-blue?style=flat-square&logo=docker)
![Redis](https://img.shields.io/badge/Redis-red?style=flat-square&logo=redis)
![SQLite](https://img.shields.io/badge/SQLite-blue?style=flat-square&logo=sqlite&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-yellow?style=flat-square&logo=javascript)
![HTML5](https://img.shields.io/badge/HTML5-orange?style=flat-square&logo=html5)
![CSS3](https://img.shields.io/badge/CSS3-blue?style=flat-square&logo=css3)
![Uvicorn](https://img.shields.io/badge/Uvicorn-green?style=flat-square)
![Pytest](https://img.shields.io/badge/Pytest-blue?style=flat-square)
![Rich](https://img.shields.io/badge/Rich-purple?style=flat-square)
![Typer](https://img.shields.io/badge/Typer-black?style=flat-square)

---

## 🚀 Kurulum ve Çalıştırma

Projeyi çalıştırmanın en kolay yolu Docker kullanmaktır.

### 1. Docker ile Çalıştırma (Önerilen)

**Gereksinimler:**
- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

1.  **Depoyu Klonlayın:**
    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

2.  **Environment Dosyasını Hazırlayın:**
    `.env.example` dosyasını kopyalayarak `.env` adında yeni bir dosya oluşturun ve gerekirse içindeki API anahtarlarını güncelleyin.
    ```bash
    cp .env.example .env
    ```

3.  **Uygulamayı Başlatın:**
    ```bash
    docker-compose up --build
    ```
    Bu komut, FastAPI uygulamasını ve Redis servisini başlatacaktır. Uygulama artık [http://localhost:8010](http://localhost:8010) adresinde erişilebilir olacaktır.

### 2. Manuel Kurulum (Alternatif)

1.  **Depoyu klonlayın ve sanal ortam oluşturun.**
2.  **Bağımlılıkları Yükleyin:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Redis Sunucusunu Başlatın:**
    Lokal makinenizde bir Redis sunucusunun çalıştığından emin olun.
4.  **API Sunucusunu Başlatın:**
    ```bash
    uvicorn api:app --host 0.0.0.0 --port 8010 --reload
    ```

## ⚙️ Kullanım

### 🌐 Web Arayüzü

Uygulama çalıştırıldıktan sonra [http://localhost:8010](http://localhost:8010) adresini ziyaret ederek modern web arayüzünü kullanabilirsiniz.

### 🖥️ Komut Satırı Arayüzü (CLI)

Etkileşimli menüyü başlatmak için:
```bash
python main.py
```
Veya `docker-compose` kullanıyorsanız:
```bash
docker-compose exec library-app python main.py
```

### 📖 API Endpoint'leri

API, [http://localhost:8010/docs](http://localhost:8010/docs) adresindeki Swagger UI üzerinden etkileşimli olarak test edilebilir. Başlıca endpoint'ler:

| Metod  | Endpoint                       | Açıklama                                                    |
| :----- | :----------------------------- | :---------------------------------------------------------- |
| `GET`  | `/books/enhanced`              | Google Books ve AI verileriyle zenginleştirilmiş kitap listesi. |
| `POST` | `/books`                       | ISBN ile (Google Books + AI) yeni bir kitap ekler.          |
| `GET`  | `/books/{isbn}/enhanced`       | Belirtilen kitabın tüm zenginleştirilmiş verilerini getirir.  |
| `POST` | `/books/{isbn}/generate-summary`| Bir kitap için AI özetini manuel olarak tetikler.           |
| `GET`  | `/books/{isbn}/similar`        | Bir kitaba benzer kitapları önerir (Google Books).          |
| `POST` | `/books/{isbn}/reviews`        | Bir kitaba puan ve yorum ekler.                             |
| `GET`  | `/tags`                        | Tüm etiketleri listeler.                                    |
| `POST` | `/books/{isbn}/tags`           | Bir kitaba etiket ekler.                                    |
| `GET`  | `/news/books/nyt`              | New York Times kitap haberleri akışını getirir.             |
| `GET`  | `/stats/extended`              | Detaylı kütüphane istatistiklerini döndürür.                |

*Not: `POST`, `PUT`, `DELETE` gibi veri değiştiren işlemler için `X-API-Key` başlığında bir API anahtarı gönderilmesi gerekmektedir.*

## ✅ Testler

Projenin tüm testlerini çalıştırmak için:
```bash
python -m pytest
```
Veya Docker içinde:
```bash
docker-compose exec library-app python -m pytest
```