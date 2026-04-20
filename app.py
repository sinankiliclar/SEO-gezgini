import streamlit as st
import os
from urllib.parse import urlparse
from helpers import (
    get_lighthouse_path,
    run_lighthouse,
    get_html_content,
    analyze_technical_seo,
    analyze_content_seo,
    analyze_report,
    optimize_image_extensions
)
import json
import tempfile
import google.generativeai as genai
import re
import time 
import base64
import io
from PIL import Image
import requests
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv() 
API_KEY = os.getenv("GEMINI_API_KEY")


try:
    genai.configure(api_key=API_KEY)
    # Daha az kota tüketen model kullanıyoruz
    model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
    gemini_available = True
except Exception as e:
    gemini_available = False
    st.warning(f"Gemini API anahtarı bulunamadı veya model yüklenemedi: {str(e)}. AI özellikleri devre dışı.")

# CSS dosyasını oku ve uygula
def load_css():
    with open("styles.css", "r") as f:
        return f.read()

# Streamlit sayfa yapılandırması
st.set_page_config(
    page_title="SEO Gezgini",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS'i yükle
st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)

# Session state'i başlat
if 'results' not in st.session_state:
    st.session_state.results = None
if 'technical_seo_results' not in st.session_state:
    st.session_state.technical_seo_results = None
if 'content_seo_results' not in st.session_state:
    st.session_state.content_seo_results = None
if 'device_type' not in st.session_state:
    st.session_state.device_type = "Mobil"
if 'url' not in st.session_state:
    st.session_state.url = ""
if 'ai_responses' not in st.session_state:
    st.session_state.ai_responses = {}
if 'last_ai_request_time' not in st.session_state:
    st.session_state.last_ai_request_time = 0
if 'image_alt_tags' not in st.session_state:
    st.session_state.image_alt_tags = {}

# Başlık ve açıklama
st.title(" SEO Gezgini")
st.markdown("""
Profesyonel SEO analizi aracı ile web sitenizin performansını optimize edin. 
Teknik SEO, içerik analizi ve performans metrikleriyle sitenizi geliştirin.
""")

# URL ve cihaz tipi girişi - daha orantılı düzen
col1, col2, col3 = st.columns([4, 3, 2])

with col1:
    # URL girişi
    url = st.text_input(
        "📥 Analiz Edilecek URL",
        value=st.session_state.url,
        placeholder="https://example.com",
        help="Analiz etmek istediğiniz web sitesinin URL'sini girin"
    )

with col2:
    # Cihaz tipi seçimi
    device_type = st.radio(
        "📱 Cihaz Tipi",
        ["Mobil", "Masaüstü"],
        index=0 if st.session_state.device_type == "Mobil" else 1,
        help="Mobil veya masaüstü görünüm için analiz yapın"
    )

with col3:
    # Analiz butonu - ortalanmış
    st.write("")  # Boşluk ekleyerek butonu ortaya al
    st.write("")
    analyze_button = st.button("🔍 Başlat", type="primary")

# AI öneri fonksiyonu - gecikme ve hata yönetimi ile güncellendi
def get_ai_recommendation(section_name, issue_details, status):
    if not gemini_available:
        return "Gemini AI erişilebilir değil. Lütfen API anahtarınızı kontrol edin."
    
    try:
        # İstekler arasında en az 10 saniye bekle
        current_time = time.time()
        if current_time - st.session_state.last_ai_request_time < 10:
            time.sleep(10 - (current_time - st.session_state.last_ai_request_time))
        
        prompt = f"""
        Bir web sitesi SEO analizi yapıyorum. {section_name} bölümünde şu sorun tespit edildi:
        
        Durum: {status}
        Sorun Detayları: {issue_details}
        
        Bu sorunu çözmek için spesifik ve uygulanabilir öneriler sunar mısın? 
        Önerilerin adım adım uygulanabilir şekilde olmalı ve teknik detay içermelidir.
        """
        
        response = model.generate_content(prompt)
        st.session_state.last_ai_request_time = time.time()
        return response.text
    except Exception as e:
        error_message = str(e)
        if "quota" in error_message.lower() or "429" in error_message:
            return "API kullanım limiti aşıldı. Lütfen bir süre bekleyip tekrar deneyin veya daha sonra tekrar kontrol edin."
        else:
            return f"AI önerisi alınırken hata oluştu: {error_message}"

# Resim için AI ile alt etiketi oluşturma fonksiyonu
def generate_alt_tag_with_ai(image_url, page_context=""):
    """Gemini AI kullanarak resim için alt etiket önerisi oluşturur"""
    if not gemini_available:
        return "Gemini AI erişilebilir değil. Lütfen API anahtarınızı kontrol edin."
    
    try:
        # İstekler arasında en az 10 saniye bekle
        current_time = time.time()
        if current_time - st.session_state.last_ai_request_time < 10:
            time.sleep(10 - (current_time - st.session_state.last_ai_request_time))
        
        # Resmi indir
        response = requests.get(image_url, timeout=15)
        if response.status_code != 200:
            return f"Resim indirilemedi. HTTP Durum Kodu: {response.status_code}"
        
        # Resmi base64 formatına dönüştür
        try:
            img = Image.open(io.BytesIO(response.content))
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
        except Exception as img_error:
            return f"Resim işlenemedi: {str(img_error)}"
        
        # Gemini'ye gönderilecek prompt
        prompt = f"""
        Bu resim için SEO uyumlu bir alt etiketi (alt text) oluştur. Alt etiketi:
        1. Resmi açıklayan ve betimleyen olmalı
        2. 125 karakteri geçmemeli
        3. Anahtar kelimeler içermeli ama spam olmamalı
        4. Sadece alt etiketi döndür, başka hiçbir açıklama ekleme
        
        Sayfa bağlamı: {page_context}
        """
        
        # Gemini API'sine istek gönder
        model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
        response = model.generate_content([
            prompt,
            {
                "mime_type": "image/jpeg",
                "data": img_str
            }
        ])
        
        st.session_state.last_ai_request_time = time.time()
        return response.text.strip()
    except Exception as e:
        return f"AI analizi sırasında hata oluştu: {str(e)}"

# Teknik SEO sonuçlarını göster
def display_technical_seo_results(technical_seo_results):
    st.subheader("⚙️ Teknik SEO Analizi")
    
    # 1. WWW
    with st.expander("🌐 WWW (www/non-www)", expanded=True):
        www_data = technical_seo_results['sections']['www']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Mevcut URL:** {www_data['current_url']}")
            st.markdown(f"**WWW Versiyonu:** {www_data['www_version']}")
            st.markdown(f"**Non-WWW Versiyonu:** {www_data['non_www_version']}")
            st.markdown(f"**Durum:** {www_data['status']}")
            st.markdown(f"**Öneri:** {www_data['recommendation']}")
        
        with col2:
            if www_data['status'] == '✅ İyi':
                st.success(www_data['status'])
            else:
                st.warning(www_data['status'])
        
        if www_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in www_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if www_data['status'] != '✅ İyi':
            section_key = f"www_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_www_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(www_data['issues']) if www_data['issues'] else "Belirtilmemiş"
                    ai_response = get_ai_recommendation("WWW (www/non-www) tutarlılığı", issues_text, www_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 2. Kırık Bağlantılar
    with st.expander("🔗 Kırık Bağlantılar", expanded=True):
        broken_data = technical_seo_results['sections']['broken_links']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Kontrol Edilen Link:** {broken_data['total_links_checked']} adet")
            st.markdown(f"**Durum:** {broken_data['status']}")
            st.markdown(f"**Öneri:** {broken_data['recommendation']}")
            
            if broken_data['broken_links']:
                st.markdown("**Kırık Linkler:**")
                for link in broken_data['broken_links']:
                    st.markdown(f"- {link['url']} (Status: {link['status']})")
        
        with col2:
            if broken_data['status'] == '✅ İyi':
                st.success(broken_data['status'])
            else:
                st.warning(broken_data['status'])
        
        if broken_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in broken_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if broken_data['status'] != '✅ İyi':
            section_key = f"broken_links_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_broken_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(broken_data['issues']) if broken_data['issues'] else "Belirtilmemiş"
                    broken_links_text = "\n".join([f"{link['url']} (Status: {link['status']})" for link in broken_data['broken_links']])
                    full_details = f"Sorunlar: {issues_text}\n\nKırık Linkler: {broken_links_text}"
                    ai_response = get_ai_recommendation("Kırık bağlantılar", full_details, broken_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 3. Robots.txt
    with st.expander("🤖 Robots.txt", expanded=True):
        robots_data = technical_seo_results['sections']['robots']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Durum:** {robots_data['status']}")
            st.markdown(f"**Öneri:** {robots_data['recommendation']}")
            
            if robots_data['exists']:
                st.markdown("**Robots.txt İçeriği:**")
                st.code(robots_data['content'], language='text')
        
        with col2:
            if robots_data['exists']:
                st.success("Mevcut")
            else:
                st.error("Eksik")
        
        if robots_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in robots_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if not robots_data['exists']:
            section_key = f"robots_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_robots_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(robots_data['issues']) if robots_data['issues'] else "Robots.txt dosyası eksik"
                    ai_response = get_ai_recommendation("Robots.txt dosyası", issues_text, robots_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])

# Metin Bazlı SEO sonuçlarını göster
def display_content_seo_results(content_seo_results):
    st.subheader("📝 Metin Bazlı SEO Analizi")
    
    # 1. Site Başlığı
    with st.expander("📄 Site Başlığı (Title)", expanded=True):
        title_data = content_seo_results['sections']['title']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Başlık:** `{title_data['title']}`")
            st.markdown(f"**Uzunluk:** {title_data['length']} karakter")
            st.markdown(f"**Durum:** {title_data['status']}")
            st.markdown(f"**Öneri:** {title_data['recommendation']}")
        
        with col2:
            if title_data['status'] == '✅ İyi':
                st.success(title_data['status'])
            elif title_data['status'] == '⚠️ Çok Kısa' or title_data['status'] == '⚠️ Çok Uzun':
                st.warning(title_data['status'])
            else:
                st.error(title_data['status'])
        
        if title_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in title_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if title_data['status'] != '✅ İyi':
            section_key = f"title_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_title_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(title_data['issues']) if title_data['issues'] else "Belirtilmemiş"
                    details = f"Mevcut Başlık: {title_data['title']}\nUzunluk: {title_data['length']} karakter\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Site başlığı (Title)", details, title_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 2. Site Açıklaması
    with st.expander("📝 Site Açıklaması (Description)", expanded=True):
        desc_data = content_seo_results['sections']['description']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Açıklama:** `{desc_data['description']}`")
            st.markdown(f"**Uzunluk:** {desc_data['length']} karakter")
            st.markdown(f"**Durum:** {desc_data['status']}")
            st.markdown(f"**Öneri:** {desc_data['recommendation']}")
        
        with col2:
            if desc_data['status'] == '✅ İyi':
                st.success(desc_data['status'])
            elif desc_data['status'] == '⚠️ Çok Kısa' or desc_data['status'] == '⚠️ Çok Uzun':
                st.warning(desc_data['status'])
            else:
                st.error(desc_data['status'])
        
        if desc_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in desc_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if desc_data['status'] != '✅ İyi':
            section_key = f"description_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_desc_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(desc_data['issues']) if desc_data['issues'] else "Belirtilmemiş"
                    details = f"Mevcut Açıklama: {desc_data['description']}\nUzunluk: {desc_data['length']} karakter\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Site açıklaması (Description)", details, desc_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 3. Site Anahtar Kelimeleri
    with st.expander("🔑 Site Anahtar Kelimeleri (Keywords)", expanded=True):
        keywords_data = content_seo_results['sections']['keywords']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Anahtar Kelimeler:** `{keywords_data['keywords']}`")
            st.markdown(f"**Kelime Listesi:** {', '.join(keywords_data['keyword_list'])}")
            st.markdown(f"**Durum:** {keywords_data['status']}")
            st.markdown(f"**Öneri:** {keywords_data['recommendation']}")
        
        with col2:
            if keywords_data['status'] == '✅ İyi':
                st.success(keywords_data['status'])
            elif keywords_data['status'] == '⚠️ Az Kelime' or keywords_data['status'] == '⚠️ Çok Fazla Kelime':
                st.warning(keywords_data['status'])
            else:
                st.error(keywords_data['status'])
        
        if keywords_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in keywords_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if keywords_data['status'] != '✅ İyi':
            section_key = f"keywords_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_keywords_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(keywords_data['issues']) if keywords_data['issues'] else "Belirtilmemiş"
                    details = f"Mevcut Anahtar Kelimeler: {keywords_data['keywords']}\nKelime Listesi: {', '.join(keywords_data['keyword_list'])}\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Site anahtar kelimeleri (Keywords)", details, keywords_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 4. Başlık Etiketler
    with st.expander("📋 Başlık Etiketler (Heading)", expanded=True):
        headings_data = content_seo_results['sections']['headings']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown("**Başlık Dağılımı:**")
            for level, count in headings_data['headings'].items():
                st.markdown(f"- {level.upper()}: {count} adet")
            
            st.markdown("**Başlık Hiyerarşisi:**")
            for item in headings_data['hierarchy'][:5]:  # İlk 5 başlığı göster
                st.markdown(f"- H{item['level']}: {item['text']}")
            
            st.markdown(f"**Durum:** {headings_data['status']}")
            st.markdown(f"**Öneri:** {headings_data['recommendation']}")
        
        with col2:
            if headings_data['status'] == '✅ İyi':
                st.success(headings_data['status'])
            else:
                st.warning(headings_data['status'])
        
        if headings_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in headings_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if headings_data['status'] != '✅ İyi':
            section_key = f"headings_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_headings_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(headings_data['issues']) if headings_data['issues'] else "Belirtilmemiş"
                    heading_dist = "\n".join([f"{level.upper()}: {count} adet" for level, count in headings_data['headings'].items()])
                    hierarchy = "\n".join([f"H{item['level']}: {item['text']}" for item in headings_data['hierarchy'][:5]])
                    details = f"Başlık Dağılımı:\n{heading_dist}\n\nBaşlık Hiyerarşisi:\n{hierarchy}\n\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Başlık etiketleri (Heading)", details, headings_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 5. Resimler - GÜNCELLENMİŞ KISIM
    with st.expander("🖼️ Resimler", expanded=True):
        images_data = content_seo_results['sections']['images']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Toplam Resim:** {images_data['total_images']} adet")
            st.markdown(f"**Alt Etiketi Olan:** {images_data['images_with_alt']} adet")
            st.markdown(f"**Alt Etiketi Olmayan:** {images_data['images_without_alt']} adet")
            
            st.markdown("**Resim Uzantıları:**")
            for ext, count in images_data['extensions'].items():
                st.markdown(f"- .{ext}: {count} adet")
            
            st.markdown(f"**Durum:** {images_data['status']}")
            st.markdown(f"**Öneri:** {images_data['recommendation']}")
        
        with col2:
            if images_data['status'] == '✅ İyi':
                st.success(images_data['status'])
            else:
                st.warning(images_data['status'])
        
        if images_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in images_data['issues']:
                st.markdown(f"- {issue}")
        
        # Resim Uzantı Optimizasyonu bölümü
        st.markdown("### 🔧 Resim Uzantı Optimizasyonu")
        optimization_data = optimize_image_extensions(images_data)
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Optimize Edilecek Resim:** {optimization_data['images_to_optimize']} adet")
            st.markdown(f"**Potansiyel Kazanç:** {optimization_data['potential_savings_kb']:.0f} KB")
            st.markdown(f"**Durum:** {optimization_data['status']}")
            st.markdown(f"**Öneri:** {optimization_data['recommendation']}")
            
            # Uzantı önerilerini göster
            st.markdown("**Uzantı Önerileri:**")
            for ext, data in optimization_data['extension_recommendations'].items():
                if data['recommended_format'] != ext:  # Sadece değişiklik önerileri
                    st.markdown(f"- .{ext} -> .{data['recommended_format']} ({data['savings_percent']}% kazanç, {data['potential_savings_kb']:.0f} KB)")
        
        with col2:
            if optimization_data['status'] == '✅ İyi':
                st.success(optimization_data['status'])
            else:
                st.warning(optimization_data['status'])
        
        if optimization_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in optimization_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if optimization_data['status'] != '✅ İyi':
            section_key = f"img_opt_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_img_opt_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(optimization_data['issues']) if optimization_data['issues'] else "Belirtilmemiş"
                    details = f"Optimize Edilecek Resim: {optimization_data['images_to_optimize']} adet\nPotansiyel Kazanç: {optimization_data['potential_savings_kb']:.0f} KB\n\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Resim uzantı optimizasyonu", details, optimization_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
        
        # Resim Uzantılarını Çevirme Bölümü - expander yerine container kullanıyoruz
        if optimization_data['status'] != '✅ İyi':
            st.markdown("### 🔄 Resim Uzantılarını Çevirme")
            
            with st.container():
                st.markdown("""
                Bu araç, resimlerinizi daha optimize edilmiş formatlara dönüştürmenize yardımcı olur.
                Dönüşüm için aşağıdaki adımları izleyin:
                """)
                
                st.markdown("**1. Dönüştürülecek uzantıyı seçin:**")
                # Sadece optimize edilebilir uzantıları göster
                convertible_extensions = [
                    ext for ext, data in optimization_data['extension_recommendations'].items() 
                    if data['recommended_format'] != ext
                ]
                
                if convertible_extensions:
                    selected_extension = st.selectbox(
                        "Uzantı seçin:",
                        options=convertible_extensions,
                        format_func=lambda x: f".{x} -> .{optimization_data['extension_recommendations'][x]['recommended_format']}"
                    )
                    
                    st.markdown("**2. Dönüşüm kodunu kopyalayın:**")
                    
                    # Seçilen uzantı için dönüşüm kodu oluştur
                    target_format = optimization_data['extension_recommendations'][selected_extension]['recommended_format']
                    
                    # HTML img etiketi için dönüşüm kodu
                    html_code = f'<!-- Resim uzantısını {selected_extension} -> {target_format} olarak değiştirin -->\n<picture>\n  <source srcset="resim-adresi.{target_format}" type="image/{target_format}">\n  <img src="resim-adresi.{selected_extension}" alt="Resim açıklaması">\n</picture>'
                    
                    st.markdown("**HTML için:**")
                    # st.code bileşeninin yerleşik kopyalama özelliğini kullan
                    st.code(html_code, language="html")
                    
                    # CSS kodu için dönüşüm kodu
                    css_code = f'/* Resim uzantısını {selected_extension} -> {target_format} olarak değiştirin */\n.background-image: url("resim-adresi.{target_format}");'
                    
                    st.markdown("**CSS için:**")
                    # st.code bileşeninin yerleşik kopyalama özelliğini kullan
                    st.code(css_code, language="css")
                    
                    # WordPress için dönüşüm kodu
                    wp_code = f"// WordPress functions.php dosyasına ekleyebilirsiniz\nadd_filter('upload_mimes', function($mimes) {{\n    $mimes['{target_format}'] = 'image/{target_format}';\n    return $mimes;\n}});"
                    
                    st.markdown("**WordPress için:**")
                    # st.code bileşeninin yerleşik kopyalama özelliğini kullan
                    st.code(wp_code, language="php")
                    
                    st.markdown("---")
                    st.markdown("""
                    **Not:** Bu kodlar sadece örnek niteliğindedir. Gerçek uygulamada:
                    1. Resimlerinizi uygun bir araçla (Squoosh, ImageOptim gibi) dönüştürün
                    2. Dönüştürülmüş resimleri sunucunuza yükleyin
                    3. Yukarıdaki kodları kendi resim adreslerinizle güncelleyin
                    """)
                    
                    st.markdown("""
                    **Kopyalama İpuçları:**
                    - Kodun sağ üst köşesindeki kopyala simgesine tıklayarak kodu panoya kopyalayabilirsiniz.
                    - Alternatif olarak, kodu seçip Ctrl+C (Windows) veya Cmd+C (Mac) tuş kombinasyonunu kullanarak kopyalayabilirsiniz.
                    """)
                else:
                    st.info("Optimize edilecek resim uzantısı bulunamadı.")
        
        # Eksik alt etiketi olan resimleri göster ve AI ile analiz etme seçeneği sun
        if images_data['images_without_alt'] > 0:
            st.markdown("### 🤖 AI Destekli Alt Etiketi Önerileri")
            
            # Sayfa içeriğinden bağlam al
            page_context = ""
            if 'page_keywords' in content_seo_results['sections']:
                top_keywords = [word for word, count in content_seo_results['sections']['page_keywords']['top_keywords'][:5]]
                page_context = f"Sayfa anahtar kelimeleri: {', '.join(top_keywords)}"
            
            # Her eksik resim için bir seçici oluştur
            selected_image = st.selectbox(
                "Analiz etmek için bir resim seçin:",
                options=range(len(images_data['images_without_alt_list'])),
                format_func=lambda i: f"Resim {i+1}: {images_data['images_without_alt_list'][i]['src'][:50]}..."
            )
            
            # Seçilen resmi göster
            img_info = images_data['images_without_alt_list'][selected_image]
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Resim URL:** {img_info['src']}")
                
                # Resmi göster
                try:
                    st.image(img_info['src'], width=300)
                except:
                    st.warning("Resim yüklenemedi.")
            
            with col2:
                # AI analiz butonu
                # Benzersiz bir anahtar oluştur
                img_key = f"img_alt_{selected_image}_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
                
                # Butona tıklandığında çalışacak fonksiyon
                def analyze_image():
                    with st.spinner("AI resmi analiz ediyor..."):
                        ai_response = generate_alt_tag_with_ai(img_info['src'], page_context)
                        st.session_state.image_alt_tags[img_key] = ai_response
                
                # Butonu oluştur
                if st.button("🤖 Alt Etiketi Öner", key=f"ai_img_alt_{img_key}"):
                    analyze_image()
                
                # Öneriyi göster
                if img_key in st.session_state.image_alt_tags:
                    st.markdown("**🤖 AI Önerisi:**")
                    st.success(st.session_state.image_alt_tags[img_key])
                    
                    # Kopyala butonu
                    st.code(st.session_state.image_alt_tags[img_key], language="text")
                    
                    st.markdown("""
                    **Kopyalama İpuçları:**
                    - Kodun sağ üst köşesindeki kopyala simgesine tıklayarak kodu panoya kopyalayabilirsiniz.
                    - Alternatif olarak, kodu seçip Ctrl+C (Windows) veya Cmd+C (Mac) tuş kombinasyonunu kullanarak kopyalayabilirsiniz.
                    """)
        
        # Genel AI Destek Butonu
        if images_data['status'] != '✅ İyi':
            section_key = f"images_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 Genel AI Destek Al", key=f"ai_images_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(images_data['issues']) if images_data['issues'] else "Belirtilmemiş"
                    extensions = "\n".join([f".{ext}: {count} adet" for ext, count in images_data['extensions'].items()])
                    details = f"Toplam Resim: {images_data['total_images']} adet\nAlt Etiketi Olan: {images_data['images_with_alt']} adet\nAlt Etiketi Olmayan: {images_data['images_without_alt']} adet\nResim Uzantıları:\n{extensions}\n\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Resim optimizasyonu", details, images_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])
    
    # 6. Sayfa Anahtar Kelimeleri
    with st.expander("📊 Sayfa Anahtar Kelimeleri", expanded=True):
        keywords_data = content_seo_results['sections']['page_keywords']
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Toplam Kelime:** {keywords_data['word_count']} adet")
            st.markdown("**En Sık Geçen Kelimeler:**")
            for word, count in keywords_data['top_keywords']:
                st.markdown(f"- {word}: {count} kez")
            
            st.markdown(f"**Durum:** {keywords_data['status']}")
            st.markdown(f"**Öneri:** {keywords_data['recommendation']}")
        
        with col2:
            if keywords_data['status'] == '✅ İyi':
                st.success(keywords_data['status'])
            else:
                st.warning(keywords_data['status'])
        
        if keywords_data['issues']:
            st.markdown("**Sorunlar:**")
            for issue in keywords_data['issues']:
                st.markdown(f"- {issue}")
        
        # AI Destek Butonu
        if keywords_data['status'] != '✅ İyi':
            section_key = f"page_keywords_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}"
            
            if st.button("🤖 AI Destek Al", key=f"ai_page_keywords_{section_key}"):
                with st.spinner("AI önerisi hazırlanıyor..."):
                    issues_text = "\n".join(keywords_data['issues']) if keywords_data['issues'] else "Belirtilmemiş"
                    top_words = "\n".join([f"{word}: {count} kez" for word, count in keywords_data['top_keywords']])
                    details = f"Toplam Kelime: {keywords_data['word_count']} adet\nEn Sık Geçen Kelimeler:\n{top_words}\n\nSorunlar: {issues_text}"
                    ai_response = get_ai_recommendation("Sayfa içi anahtar kelime analizi", details, keywords_data['status'])
                    st.session_state.ai_responses[section_key] = ai_response
            
            if section_key in st.session_state.ai_responses:
                st.markdown("**🤖 AI Önerisi:**")
                st.info(st.session_state.ai_responses[section_key])

# Sonuçları göster
def display_results(results, device_type, technical_seo_results=None, content_seo_results=None):
    device_emoji = '📱' if device_type == "Mobil" else '🖥️'
    st.header(f"{device_emoji} {device_type} Cihaz İçin Sonuçlar")
    
    # Kategori bilgileri
    category_info = {
        'performance': {'emoji': '⚡', 'title': 'Performans', 'color': '#FF6B6B'},
        'seo': {'emoji': '🔍', 'title': 'SEO', 'color': '#4ECDC4'},
        'best-practices': {'emoji': '⭐', 'title': 'En İyi Uygulamalar', 'color': '#FFD166'},
        'accessibility': {'emoji': '♿', 'title': 'Erişilebilirlik', 'color': '#6A0572'},
        'technical-seo': {'emoji': '⚙️', 'title': 'Teknik SEO', 'color': '#2196F3'},
        'content-seo': {'emoji': '📝', 'title': 'Metin Bazlı SEO', 'color': '#9C27B0'}
    }
    
    # Genel skorlar (sadece Lighthouse kategorileri)
    st.subheader("📊 Genel Skorlar")
    cols = st.columns(4)  # 4 kategori (performans, SEO, en iyi uygulamalar, erişilebilirlik)
    
    # Sadece Lighthouse kategorilerini göster (teknik ve metin SEO hariç)
    lighthouse_categories = ['performance', 'seo', 'best-practices', 'accessibility']
    for i, category in enumerate(lighthouse_categories):
        if category in results:
            data = results[category]
            info = category_info.get(category, {'title': category.upper(), 'color': '#888888'})
            with cols[i]:
                st.markdown(f"""
                <div style="background-color: {info['color']}; padding: 15px; border-radius: 10px; text-align: center;">
                    <h3 style="color: white; margin: 0;">{info['emoji']} {info['title']}</h3>
                    <h2 style="color: white; margin: 10px 0 0 0;">{data['score']}/100</h2>
                </div>
                """, unsafe_allow_html=True)
    
    # Detaylı sorunlar
    st.subheader("🔍 Detaylı Sorunlar")
    
    for category, data in results.items():
        info = category_info.get(category, {'title': category.upper(), 'emoji': '📊'})
        
        with st.expander(f"{info['emoji']} {info['title']} (Skor: {data['score']}/100)"):
            if not data['issues']:
                st.success("✅ Kırmızı veya sarı uyarı bulunamadı!")
            else:
                for issue in data['issues']:
                    with st.container():
                        # Sorun kutusu
                        st.markdown(f"""
                        <div style="
                            padding: 15px; 
                            border-radius: 8px; 
                            margin-bottom: 15px; 
                            border-left: 5px solid {'#d32f2f' if issue['severity'] == '🔴' else '#f57c00'};
                            background-color: #ffffff;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        ">
                            <h4 style="
                                margin-top: 0; 
                                margin-bottom: 10px; 
                                color: #333333; 
                                font-size: 18px; 
                                font-weight: 600;
                            ">
                                {issue['severity']} - {issue['title']}
                            </h4>
                            <p style="
                                margin: 5px 0; 
                                color: #555555; 
                                font-size: 16px; 
                                line-height: 1.5;
                            ">
                                <strong style="color: #333333;">Skor:</strong> 
                                <span style="color: {'#d32f2f' if issue['severity'] == '🔴' else '#f57c00'}; font-weight: bold;">
                                    {issue['score']}
                                </span>
                            </p>
                            <p style="
                                margin: 5px 0; 
                                color: #555555; 
                                font-size: 16px; 
                                line-height: 1.5;
                            ">
                                <strong style="color: #333333;">Açıklama:</strong> 
                                {issue['description']}
                            </p>
                        """, unsafe_allow_html=True)
                        
                        if issue['details']:
                            st.markdown(f"""
                            <p style="
                                margin: 5px 0; 
                                color: #555555; 
                                font-size: 16px; 
                                line-height: 1.5;
                            ">
                                <strong style="color: #333333;">Detay:</strong> 
                                {issue['details']}
                            </p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown("</div>", unsafe_allow_html=True)
    
    # Teknik SEO detaylı sonuçları  
    if technical_seo_results:
        display_technical_seo_results(technical_seo_results)
    
    # Metin Bazlı SEO detaylı sonuçları
    if content_seo_results:
        display_content_seo_results(content_seo_results)
    
    # İndirme bölümünü en sona ekle
    st.markdown("---")
    st.subheader("📥 Raporu İndir")
    
    # JSON raporu oluştur
    report_data = {
        "url": st.session_state.url,
        "device_type": st.session_state.device_type,
        "lighthouse_results": results,
        "technical_seo": technical_seo_results,
        "content_seo": content_seo_results,
        "ai_recommendations": st.session_state.ai_responses,
        "image_alt_tags": st.session_state.image_alt_tags
    }
    
    # Geçici dosya oluştur - METİN MODUNDA
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp_file:
        json.dump(report_data, tmp_file, ensure_ascii=False, indent=4)
        temp_filename = tmp_file.name
    
    # İndirme butonu - BENZERSİZ ANAHTAR
    with open(temp_filename, "rb") as f:
        st.download_button(
            label="📥 JSON Raporunu İndir",
            data=f,
            file_name=f"seo_analiz_{st.session_state.url.replace('https://', '').replace('http://', '').replace('/', '_')}.json",
            mime="application/json",
            key=f"download_button_{int(time.time())}",  # BENZERSİZ ANAHTAR
            help="Tüm analiz sonuçlarını içeren JSON raporunu indirin"
        )
    
    # Geçici dosyayı sil
    try:
        os.remove(temp_filename)
    except:
        pass

# Ana uygulama
if analyze_button:
    if not url:
        st.error("❌ Lütfen bir URL girin!")
    else:
        # URL'yi kontrol et
        try:
            parsed_url = urlparse(url)
            if not all([parsed_url.scheme, parsed_url.netloc]):
                st.error("❌ Geçersiz URL formatı! Lütfen tam URL girin (ör: https://example.com)")
            else:
                # Session state'i güncelle
                st.session_state.url = url
                st.session_state.device_type = device_type
                st.session_state.ai_responses = {}  # AI yanıtlarını sıfırla
                st.session_state.image_alt_tags = {}  # Resim alt etiketlerini sıfırla
                
                # Lighthouse çalıştır
                try:
                    # İlerleme çubuğu ekle
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("🚀 Lighthouse analizi yapılıyor...")
                    progress_bar.progress(10)
                    
                    json_file = run_lighthouse(url, device_type)
                    progress_bar.progress(40)
                    
                    # Raporu analiz et
                    status_text.text("📊 Rapor analiz ediliyor...")
                    results = analyze_report(json_file)
                    st.session_state.results = results
                    progress_bar.progress(60)
                    
                    # İçerik SEO analizi yap
                    status_text.text("📄 İçerik SEO analizi yapılıyor...")
                    html_content = get_html_content(url)
                    if html_content:
                        technical_seo_results = analyze_technical_seo(html_content, url)
                        content_seo_results = analyze_content_seo(html_content, url)
                        st.session_state.technical_seo_results = technical_seo_results
                        st.session_state.content_seo_results = content_seo_results
                    
                    progress_bar.progress(100)
                    status_text.text("✅ Analiz tamamlandı!")
                    
                    # Sonuçları göster
                    display_results(st.session_state.results, st.session_state.device_type, st.session_state.technical_seo_results, st.session_state.content_seo_results)
                    
                    # Geçici dosyayı sil
                    try:
                        os.remove(json_file)
                    except:
                        pass
                except Exception as e:
                    st.error(f"❌ Bir hata oluştu: {e}")
        except Exception as e:
            st.error(f"❌ Bir hata oluştu: {e}")
elif st.session_state.results:
    # Önceki sonuçları göster
    display_results(st.session_state.results, st.session_state.device_type, st.session_state.technical_seo_results, st.session_state.content_seo_results)