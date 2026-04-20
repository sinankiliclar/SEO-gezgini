import subprocess
import json
import os
import shutil
import tempfile
import requests
from bs4 import BeautifulSoup
import re
from collections import Counter
from urllib.parse import urlparse

def get_lighthouse_path():
    """Lighthouse'un sistem yolunu bulur"""
    return shutil.which('lighthouse')

def run_lighthouse(url, device_type):
    """Lighthouse çalıştırır ve JSON raporu oluşturur"""
    # Geçici dosya oluştur
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp_file:
        filename = tmp_file.name
    
    # Lighthouse yolunu al
    lighthouse_path = get_lighthouse_path()
    if not lighthouse_path:
        raise Exception("Lighthouse bulunamadı. Lighthouse kurulu olduğundan emin olun.")
    
    # Chrome flag'lerini cihaz tipine göre ayarla
    if device_type == "Masaüstü":
        chrome_flags = "--headless --no-sandbox --window-size=1920,1080"
        form_factor = "desktop"
    else:
        chrome_flags = "--headless --no-sandbox --window-size=412,915"
        form_factor = "mobile"
    
    # Lighthouse komutu - performans için güncellendi
    cmd = [
        lighthouse_path,
        url,
        "--output=json",
        f"--output-path={filename}",
        "--quiet",
        f"--chrome-flags={chrome_flags}",
        f"--form-factor={form_factor}",
        "--throttling-method=provided",  # Daha hızlı analiz için
        "--max-wait-for-load=30000",     # Maksimum bekleme süresini 30 saniye ile sınırla
        "--enable-error-reporting=false"  # Hata raporlamayı devre dışı bırak
    ]
    
    # Masaüstü için ek parametre
    if device_type == "Masaüstü":
        cmd.append("--screenEmulation.disabled")
    
    try:
        subprocess.run(cmd, check=True)
        return filename
    except subprocess.CalledProcessError as e:
        raise Exception(f"Lighthouse çalıştırılamadı: {e}")
    except FileNotFoundError:
        raise Exception(f"Lighthouse bulunamadı: {lighthouse_path}")

def get_html_content(url):
    """Sayfanın HTML içeriğini indirir"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"HTML içerik alınamadı: {e}")

def check_robots_txt(url):
    """Robots.txt dosyasını kontrol eder"""
    parsed_url = urlparse(url)
    robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
    
    try:
        response = requests.get(robots_url, timeout=5)
        if response.status_code == 200:
            return {
                'exists': True,
                'content': response.text,
                'status': 'Mevcut'
            }
        else:
            return {
                'exists': False,
                'content': '',
                'status': f'HTTP {response.status_code}'
            }
    except:
        return {
            'exists': False,
            'content': '',
            'status': 'Erişilemedi'
        }

def check_broken_links(html, base_url):
    """Kırık linkleri kontrol eder"""
    soup = BeautifulSoup(html, 'html.parser')
    links = soup.find_all('a', href=True)
    broken_links = []
    
    for link in links[:20]:  # Performans için ilk 20 linki kontrol et
        href = link.get('href')
        if href and not href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            if href.startswith('/'):
                href = base_url + href
            elif href.startswith('http'):
                pass
            else:
                continue
                
            try:
                response = requests.head(href, timeout=3, allow_redirects=True)
                if response.status_code >= 400:
                    broken_links.append({
                        'url': href,
                        'status': response.status_code
                    })
            except:
                broken_links.append({
                    'url': href,
                    'status': 'Erişilemedi'
                })
    
    return broken_links

def analyze_technical_seo(html, url):
    """Teknik SEO analizini yapar"""
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    results = {
        'score': 100,
        'sections': {}
    }
    
    # 1. WWW (www/non-www tutarlılığı)
    www_analysis = {
        'current_url': url,
        'www_version': '',
        'non_www_version': '',
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if url.startswith('https://www.'):
        www_analysis['www_version'] = url
        www_analysis['non_www_version'] = url.replace('https://www.', 'https://')
    else:
        www_analysis['www_version'] = url.replace('https://', 'https://www.')
        www_analysis['non_www_version'] = url
    
    # Her iki versiyonu da kontrol et
    try:
        www_response = requests.head(www_analysis['www_version'], timeout=3)
        non_www_response = requests.head(www_analysis['non_www_version'], timeout=3)
        
        if www_response.status_code == 200 and non_www_response.status_code == 200:
            www_analysis['issues'].append('Hem www hem de non-www versiyon erişilebilir')
            www_analysis['status'] = '⚠️ Tutarsız'
            www_analysis['recommendation'] = 'Bir versiyonu tercih edip diğerini yönlendirin.'
            results['score'] -= 10
        else:
            www_analysis['status'] = '✅ İyi'
            www_analysis['recommendation'] = 'WWW tutarlılığı sağlanmış.'
    except:
        www_analysis['status'] = '⚠️ Kontrol Edilemedi'
        www_analysis['recommendation'] = 'WWW versiyonları kontrol edilemedi.'
    
    results['sections']['www'] = www_analysis
    
    # 2. Kırık Bağlantılar
    broken_links = check_broken_links(html, base_url)
    broken_analysis = {
        'total_links_checked': min(20, len(BeautifulSoup(html, 'html.parser').find_all('a', href=True))),
        'broken_links': broken_links,
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if broken_links:
        broken_analysis['issues'].append(f'{len(broken_links)} adet kırık link bulundu')
        results['score'] -= min(20, len(broken_links) * 5)
        broken_analysis['status'] = '⚠️ Kırık Linkler'
        broken_analysis['recommendation'] = 'Kırık linkleri düzeltin.'
    else:
        broken_analysis['status'] = '✅ İyi'
        broken_analysis['recommendation'] = 'Kırık link bulunamadı.'
    
    results['sections']['broken_links'] = broken_analysis
    
    # 3. Robots.txt
    robots_info = check_robots_txt(url)
    robots_analysis = {
        'exists': robots_info['exists'],
        'content': robots_info['content'][:500] + '...' if len(robots_info['content']) > 500 else robots_info['content'],
        'status': robots_info['status'],
        'recommendation': '',
        'issues': []
    }
    
    if not robots_info['exists']:
        robots_analysis['issues'].append('Robots.txt dosyası bulunamadı')
        robots_analysis['recommendation'] = 'Robots.txt dosyası oluşturun.'
        results['score'] -= 5
    else:
        robots_analysis['recommendation'] = 'Robots.txt dosyası mevcut.'
    
    results['sections']['robots'] = robots_analysis
    
    results['score'] = max(0, min(100, results['score']))
    
    return results

def analyze_content_seo(html, url):
    """Metin bazlı SEO analizini yapar"""
    soup = BeautifulSoup(html, 'html.parser')
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    results = {
        'score': 100,
        'sections': {}
    }
    
    # 1. Site Başlığı (Title)
    title_tag = soup.find('title')
    title_analysis = {
        'title': title_tag.get_text().strip() if title_tag else '',
        'length': len(title_tag.get_text().strip()) if title_tag else 0,
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if not title_tag:
        title_analysis['status'] = '❌ Eksik'
        title_analysis['recommendation'] = 'Sayfada title etiketi bulunamadı. Title ekleyin.'
        title_analysis['issues'].append('Title etiketi eksik')
        results['score'] -= 20
    else:
        if title_analysis['length'] < 30:
            title_analysis['status'] = '⚠️ Çok Kısa'
            title_analysis['recommendation'] = 'Title 30-60 karakter arasında olmalıdır.'
            title_analysis['issues'].append(f'Title çok kısa ({title_analysis["length"]} karakter)')
            results['score'] -= 10
        elif title_analysis['length'] > 60:
            title_analysis['status'] = '⚠️ Çok Uzun'
            title_analysis['recommendation'] = 'Title 30-60 karakter arasında olmalıdır.'
            title_analysis['issues'].append(f'Title çok uzun ({title_analysis["length"]} karakter)')
            results['score'] -= 5
        else:
            title_analysis['status'] = '✅ İyi'
            title_analysis['recommendation'] = 'Title uzunluğu uygun.'
    
    results['sections']['title'] = title_analysis
    
    # 2. Site Açıklaması (Description)
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    desc_analysis = {
        'description': meta_desc.get('content', '').strip() if meta_desc else '',
        'length': len(meta_desc.get('content', '').strip()) if meta_desc else 0,
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if not meta_desc or not desc_analysis['description']:
        desc_analysis['status'] = '❌ Eksik'
        desc_analysis['recommendation'] = 'Meta description ekleyin.'
        desc_analysis['issues'].append('Meta description eksik')
        results['score'] -= 20
    else:
        if desc_analysis['length'] < 120:
            desc_analysis['status'] = '⚠️ Çok Kısa'
            desc_analysis['recommendation'] = 'Meta description 120-160 karakter arasında olmalıdır.'
            desc_analysis['issues'].append(f'Description çok kısa ({desc_analysis["length"]} karakter)')
            results['score'] -= 10
        elif desc_analysis['length'] > 160:
            desc_analysis['status'] = '⚠️ Çok Uzun'
            desc_analysis['recommendation'] = 'Meta description 120-160 karakter arasında olmalıdır.'
            desc_analysis['issues'].append(f'Description çok uzun ({desc_analysis["length"]} karakter)')
            results['score'] -= 5
        else:
            desc_analysis['status'] = '✅ İyi'
            desc_analysis['recommendation'] = 'Description uzunluğu uygun.'
    
    results['sections']['description'] = desc_analysis
    
    # 3. Site Anahtar Kelimeleri (Keywords)
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    keywords_analysis = {
        'keywords': meta_keywords.get('content', '').strip() if meta_keywords else '',
        'keyword_list': [],
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if meta_keywords and keywords_analysis['keywords']:
        keywords_analysis['keyword_list'] = [k.strip() for k in keywords_analysis['keywords'].split(',') if k.strip()]
        if len(keywords_analysis['keyword_list']) < 3:
            keywords_analysis['status'] = '⚠️ Az Kelime'
            keywords_analysis['recommendation'] = 'Daha fazla anahtar kelime ekleyin.'
            keywords_analysis['issues'].append('Anahtar kelime sayısı az')
            results['score'] -= 5
        elif len(keywords_analysis['keyword_list']) > 10:
            keywords_analysis['status'] = '⚠️ Çok Fazla Kelime'
            keywords_analysis['recommendation'] = 'Anahtar kelime sayısını azaltın.'
            keywords_analysis['issues'].append('Anahtar kelime sayısı çok fazla')
            results['score'] -= 5
        else:
            keywords_analysis['status'] = '✅ İyi'
            keywords_analysis['recommendation'] = 'Anahtar kelime sayısı uygun.'
    else:
        keywords_analysis['status'] = '❌ Eksik'
        keywords_analysis['recommendation'] = 'Meta keywords etiketi ekleyin.'
        keywords_analysis['issues'].append('Meta keywords etiketi eksik')
        results['score'] -= 10
    
    results['sections']['keywords'] = keywords_analysis
    
    # 4. Başlık Etiketler (Heading)
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    heading_analysis = {
        'headings': {},
        'hierarchy': [],
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    # Başlık sayımlarını topla
    for i in range(1, 7):
        heading_analysis['headings'][f'h{i}'] = len(soup.find_all(f'h{i}'))
    
    # H1 kontrolü
    if heading_analysis['headings']['h1'] == 0:
        heading_analysis['issues'].append('H1 başlığı eksik')
        results['score'] -= 15
    elif heading_analysis['headings']['h1'] > 1:
        heading_analysis['issues'].append(f'Birden fazla H1 başlığı ({heading_analysis["headings"]["h1"]} adet)')
        results['score'] -= 10
    
    # Hiyerarşi kontrolü
    heading_levels = []
    for heading in headings:
        level = int(heading.name[1])
        heading_levels.append(level)
        heading_analysis['hierarchy'].append({
            'level': level,
            'text': heading.get_text().strip()[:50] + '...' if len(heading.get_text().strip()) > 50 else heading.get_text().strip()
        })
    
    for i in range(1, len(heading_levels)):
        if heading_levels[i] - heading_levels[i-1] > 1:
            heading_analysis['issues'].append(f'Başlık hiyerarşisi bozuk (H{heading_levels[i-1]} sonra H{heading_levels[i]})')
            results['score'] -= 10
    
    if not heading_analysis['issues']:
        heading_analysis['status'] = '✅ İyi'
        heading_analysis['recommendation'] = 'Başlık yapısı uygun.'
    else:
        heading_analysis['status'] = '⚠️ İyileştirme Gerekli'
        heading_analysis['recommendation'] = 'Başlık yapısını düzeltin.'
    
    results['sections']['headings'] = heading_analysis
    
    # 5. Resimler - GÜNCELLENMİŞ KISIM
    images = soup.find_all('img')
    image_analysis = {
        'total_images': len(images),
        'images_with_alt': 0,
        'images_without_alt': 0,
        'images_without_alt_list': [],  # Eksik alt etiketi olan resimlerin listesi
        'extensions': {},
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    for img in images:
        src = img.get('src', '')
        if src:
            # Tam URL'yi oluştur
            if src.startswith('//'):
                src = f"{parsed_url.scheme}:{src}"
            elif src.startswith('/'):
                src = f"{base_url}{src}"
            elif not src.startswith(('http://', 'https://')):
                src = f"{base_url}/{src.lstrip('/')}"
            
            # Uzantıyı al
            ext = src.split('.')[-1].split('?')[0].lower()
            if ext in image_analysis['extensions']:
                image_analysis['extensions'][ext] += 1
            else:
                image_analysis['extensions'][ext] = 1
        
        # Alt kontrolü
        alt_text = img.get('alt', '').strip()
        if alt_text:
            image_analysis['images_with_alt'] += 1
        else:
            image_analysis['images_without_alt'] += 1
            # Eksik alt etiketi olan resimleri listeye ekle
            # Sadece geçerli URL'leri ekle
            if src and src.startswith(('http://', 'https://')):
                image_analysis['images_without_alt_list'].append({
                    'src': src,
                    'alt': alt_text
                })
    
    if image_analysis['images_without_alt'] > 0:
        image_analysis['issues'].append(f'{image_analysis["images_without_alt"]} adet resimde alt etiketi eksik')
        results['score'] -= min(20, image_analysis['images_without_alt'] * 2)
    
    if not image_analysis['issues']:
        image_analysis['status'] = '✅ İyi'
        image_analysis['recommendation'] = 'Tüm resimlerde alt etiketi mevcut.'
    else:
        image_analysis['status'] = '⚠️ İyileştirme Gerekli'
        image_analysis['recommendation'] = 'Eksik alt etiketlerini ekleyin.'
    
    results['sections']['images'] = image_analysis
    
    # 6. Sayfa Anahtar Kelimeleri (İçerikteki önemli kelimeler)
    body_text = soup.get_text()
    
    # Türkçe karakterleri destekleyen kelime ayıklama
    words = re.findall(r'\b[^\d\W_]+\b', body_text.lower(), re.UNICODE)
    
    # Genişletilmiş Türkçe stop words listesi
    stop_words = {
        've', 'bir', 'için', 'bu', 'ile', 'de', 'da', 'en', 'çok', 'ama', 'ki', 'gibi', 'olarak', 'daha', 'kadar', 'sonra', 'veya', 'ile', 'için',
        'acaba', 'ama', 'aslında', 'az', 'bazı', 'belki', 'biri', 'birkaç', 'birşey', 'biz', 'bu', 'çok', 'çünkü', 'da', 'daha', 'de', 'defa', 
        'diye', 'eğer', 'en', 'gibi', 'hem', 'hep', 'hepsi', 'her', 'hiç', 'için', 'ile', 'ise', 'kez', 'ki', 'kim', 'mı', 'mu', 'mü', 
        'nasıl', 'ne', 'neden', 'nerde', 'nerede', 'nereye', 'niçin', 'niye', 'o', 'sanki', 'şey', 'siz', 'şu', 'tüm', 've', 'veya', 'ya', 'yani',
        'ben', 'sen', 'o', 'biz', 'siz', 'onlar', 'my', 'senin', 'onun', 'bizim', 'sizin', 'onların', 'bana', 'sana', 'ona', 'bize', 'size', 'onlara',
        'beni', 'seni', 'onu', 'bizi', 'sizi', 'onları', 'benim', 'senin', 'onun', 'bizim', 'sizin', 'onların', 'bende', 'sende', 'onda', 'bizde', 'sizde', 'onlarda',
        'benden', 'senden', 'ondan', 'bizden', 'sizden', 'onlardan', 'benle', 'senle', 'onla', 'bizle', 'sizle', 'onlarla', 'i', 'in', 'un', 'ümüz', 'ünüz', 'ları',
        'mı', 'mi', 'mu', 'mü', 'mış', 'miş', 'musun', 'müsün', 'mısın', 'misin', 'dır', 'dir', 'dur', 'dür', 'tır', 'tir', 'tur', 'tür', 'yım', 'yim', 'sin', 'sun', 'yız', 'sınız', 'lar', 'ler'
    }
    
    # Stop words olmayan kelimeleri filtrele ve en az 3 harfli olanları al
    filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
    word_freq = Counter(filtered_words)
    
    # En sık geçen 10 kelime
    top_keywords = word_freq.most_common(10)
    
    keyword_analysis = {
        'word_count': len(words),
        'top_keywords': top_keywords,
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    if len(words) < 300:
        keyword_analysis['issues'].append(f'İçerik çok kısa ({len(words)} kelime)')
        results['score'] -= 15
        keyword_analysis['status'] = '⚠️ Kısa İçerik'
        keyword_analysis['recommendation'] = 'Daha uzun içerik ekleyin.'
    else:
        keyword_analysis['status'] = '✅ İyi'
        keyword_analysis['recommendation'] = 'İçerik uzunluğu uygun.'
    
    results['sections']['page_keywords'] = keyword_analysis
    
    # Skoru 0-100 arasına sınırla
    results['score'] = max(0, min(100, results['score']))
    
    return results

def optimize_image_extensions(image_analysis):
    """
    Resim uzantılarını SEO için daha uygun formata çevirir.
    Önerilen dönüşümler:
    - PNG -> WebP (saydaf resimler için)
    - JPG/JPEG -> WebP (fotoğraflar için)
    - GIF -> WebP (basit animasyonlar için) veya PNG (durdurulmuş animasyonlar için)
    
    Args:
        image_analysis (dict): Resim analizi sonuçları içeren sözlük
        
    Returns:
        dict: Optimizasyon önerileri içeren sözlük
    """
    optimization_recommendations = {
        'total_images': image_analysis['total_images'],
        'images_to_optimize': 0,
        'potential_savings_kb': 0,
        'extension_recommendations': {},
        'status': '',
        'recommendation': '',
        'issues': []
    }
    
    # Uzantı dönüşüm önerileri ve potansiyel boyut kazançları
    extension_mapping = {
        'png': {
            'recommended': 'webp',
            'savings_percent': 26,  # PNG'den WebP'e dönüşümde ortalama %26 boyut kazancı
            'reason': 'Daha iyi sıkıştırma ve saydamlık desteği'
        },
        'jpg': {
            'recommended': 'webp',
            'savings_percent': 25,  # JPEG'den WebP'e dönüşümde ortalama %25 boyut kazancı
            'reason': 'Daha iyi sıkıştırma ile kalite kaybı olmadan boyut azaltma'
        },
        'jpeg': {
            'recommended': 'webp',
            'savings_percent': 25,
            'reason': 'Daha iyi sıkıştırma ile kalite kaybı olmadan boyut azaltma'
        },
        'gif': {
            'recommended': 'webp',
            'savings_percent': 19,  # GIF'ten WebP'e dönüşümde ortalama %19 boyut kazancı
            'reason': 'Daha iyi sıkıştırma ve animasyon desteği'
        }
    }
    
    # Her uzantı için optimizasyon önerileri oluştur
    for ext, count in image_analysis['extensions'].items():
        ext_lower = ext.lower()
        
        if ext_lower in extension_mapping:
            recommended = extension_mapping[ext_lower]['recommended']
            savings_percent = extension_mapping[ext_lower]['savings_percent']
            reason = extension_mapping[ext_lower]['reason']
            
            # Ortalama resim boyutunu 100KB olarak varsayalım
            avg_size_kb = 100
            potential_savings = count * avg_size_kb * (savings_percent / 100)
            
            optimization_recommendations['extension_recommendations'][ext] = {
                'count': count,
                'recommended_format': recommended,
                'savings_percent': savings_percent,
                'potential_savings_kb': potential_savings,
                'reason': reason
            }
            
            optimization_recommendations['images_to_optimize'] += count
            optimization_recommendations['potential_savings_kb'] += potential_savings
        else:
            # Zaten optimize edilmiş veya bilinmeyen uzantılar
            optimization_recommendations['extension_recommendations'][ext] = {
                'count': count,
                'recommended_format': ext,  # Değişiklik önermiyoruz
                'savings_percent': 0,
                'potential_savings_kb': 0,
                'reason': 'Bu format zaten optimize edilmiş veya öneri yapılamıyor'
            }
    
    # Durum ve önerileri belirle
    if optimization_recommendations['images_to_optimize'] > 0:
        optimization_recommendations['status'] = '⚠️ Optimizasyon Gerekli'
        optimization_recommendations['recommendation'] = f'{optimization_recommendations["images_to_optimize"]} adet resmin uzantısını değiştirerek yaklaşık {optimization_recommendations["potential_savings_kb"]:.0f} KB kazanç sağlayabilirsiniz.'
        optimization_recommendations['issues'] = [
            f'{ext} uzantılı {data["count"]} adet resim {data["recommended_format"]} formatına dönüştürülebilir' 
            for ext, data in optimization_recommendations['extension_recommendations'].items() 
            if data['recommended_format'] != ext
        ]
    else:
        optimization_recommendations['status'] = '✅ İyi'
        optimization_recommendations['recommendation'] = 'Resimler zaten optimize edilmiş formatta.'
    
    return optimization_recommendations

def analyze_report(json_file):
    """Lighthouse JSON raporunu analiz eder"""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    categories = ['performance', 'accessibility', 'best-practices', 'seo']
    results = {}
    
    for category in categories:
        if category not in data['categories']:
            continue
            
        category_data = data['categories'][category]
        results[category] = {
            'score': round(category_data['score'] * 100),
            'issues': []
        }
        
        for audit_ref in category_data['auditRefs']:
            audit_id = audit_ref['id']
            audit = data['audits'][audit_id]
            
            if audit['score'] is None:
                continue
                
            if audit['score'] < 0.9:
                score_display = audit.get('scoreDisplayValue')
                if score_display is None:
                    score_display = str(audit['score'])
                
                if audit['score'] < 0.5:
                    #severity = '🔴 Kırmızı'
                    severity = '🔴'
                else:
                    #severity = '🟡 Sarı'
                    severity = '🟡'
                
                results[category]['issues'].append({
                    'id': audit_id,
                    'title': audit['title'],
                    'score': score_display,
                    'description': audit['description'],
                    'details': audit.get('displayValue', ''),
                    'severity': severity
                })
    
    return results