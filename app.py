# -*- coding: utf-8 -*-
"""
Created on Thu Jan  1 14:42:09 2026
@author: robin
"""
import streamlit as st
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
from time import mktime
import json
import re
import warnings
import pandas as pd
from pygooglenews import GoogleNews
import time

# On ignore les warnings
warnings.filterwarnings("ignore")

# ==============================================================================
# 1. CONFIGURATION (DOIT ETRE LA PREMIERE COMMANDE STREAMLIT)
# ==============================================================================

# CORRECTIF : Cette ligne doit impérativement être la première commande Streamlit
st.set_page_config(page_title="Strat Watch (7j) Protected", layout="centered", page_icon="🛡️")


# 🔴🔴 CLES API 🔴🔴
# On récupère les clés depuis les secrets du Cloud
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    st.error("Les clés API ne sont pas configurées dans les secrets Streamlit.")
    st.stop()

# Protection Configuration Gemini
try:
    if "VOTRE" not in GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.sidebar.error(f"Erreur Configuration Gemini: {e}")

# --- CSS STYLING (High Contrast Fix) ---
st.markdown("""
<style>
    .block-container { max-width: 800px; padding-top: 2rem; }
    
    /* Force Dark Card styles */
    .news-card { 
        background-color: #1E1E1E !important; 
        padding: 20px; 
        border-radius: 8px; 
        margin-bottom: 15px; 
        border: 1px solid #333; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        color: #E0E0E0 !important; 
    }
    
    .news-meta { 
        font-size: 0.75em; 
        text-transform: uppercase; 
        color: #9E9E9E !important; 
        margin-bottom: 8px; 
        display: flex; 
        justify-content: space-between;
        border-bottom: 1px solid #333;
        padding-bottom: 8px;
    }
    
    .news-title a { 
        color: #FFFFFF !important; 
        text-decoration: none; 
        font-size: 1.2em; 
        font-weight: 700; 
    }
    .news-title a:hover { color: #4CAF50 !important; }
    
    .news-summary { 
        font-size: 0.95em; 
        color: #CCCCCC !important; 
        line-height: 1.6; 
        margin-top: 10px; 
        text-align: justify; 
    }
    
    /* Indicateurs IA */
    .ai-badge { font-size: 0.7em; font-weight: bold; padding: 2px 8px; border-radius: 4px; color: #fff !important; margin-right: 10px;}
    .badge-HIGH { background-color: #D32F2F !important; } /* Rouge */
    .badge-MEDIUM { background-color: #F57C00 !important; } /* Orange */
    .badge-LOW { background-color: #388E3C !important; } /* Vert */
    
    .ai-analysis { 
        margin-top: 12px; 
        padding: 10px; 
        background-color: rgba(33, 150, 243, 0.1) !important; 
        border-left: 3px solid #2196F3; 
        color: #90CAF9 !important; 
        font-size: 0.9em;
        font-style: italic;
    }

    .section-header {
        margin-top: 40px; margin-bottom: 20px;
        font-size: 1.4em; font-weight: bold; 
        color: #000000; 
        border-bottom: 2px solid #555; padding-bottom: 5px;
    }
    
    @media (prefers-color-scheme: dark) {
        .section-header { color: #FFF; }
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIG SOURCES ---
RSS_CONFIG = {
    "MACRO": [
        {"name": "CNBC Finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"}, 
        {"name": "Les Echos Entreprises", "url": "https://news.google.com/rss/search?q=site:lesechos.fr+entreprises+when:7d&hl=fr&gl=FR&ceid=FR:fr"},
        {"name": "La Tribune", "url": "https://www.latribune.fr/feed.xml"}
    ],
    "SECTEUR": [
        {"name": "Usine Nouvelle", "url": "https://www.usinenouvelle.com/rss/"},
        {"name": "Les Echos Tech", "url": "https://news.google.com/rss/search?q=site:lesechos.fr+tech+medias+when:7d&hl=fr&gl=FR&ceid=FR:fr"}
    ]
}

TARGETS_ESN = [
    "Capgemini", "Accenture", "Sopra Steria", "Atos", "IBM", "CGI", "Inetum", 
    "Econocom", "Neurones", "Akkodis", "Expleo", "Assystem", "SII", "Wavestone", 
    "Sia Partners", "Kyndryl", "DXC Technology", "Tata Consultancy Services", 
    "NTT Data", "Fujitsu", "Cognizant", "Infosys", "HCLTech", "Wipro", 
    "Tech Mahindra", "LTIMindtree", "EPAM Systems", "Globant", "Endava", "Reply", 
    "Nagarro", "Persistent Systems", "Genpact", "WNS", "Orange Business", 
    "Thales Services Numériques", "SPIE ICS", "Equans Digital", "Docaposte", 
    "Cegedim", "Computacenter", "SCC", "Altran", "Adecco Engineering", 
    "BearingPoint", "McKinsey Digital", "BCG X", "Bain & Company"
]

# ==============================================================================
# 2. LOGIQUE METIER & FILTRE DATE STRICT
# ==============================================================================

# SYSTEME DE LOG AMELIORÉ
st.sidebar.header("🔍 Debug & Filtres")
debug_container = st.sidebar.container()

def log_status(msg, type="info"):
    """Affiche un log propre dans la sidebar"""
    if type == "success":
        debug_container.success(msg, icon="✅")
    elif type == "error":
        debug_container.error(msg, icon="❌")
    elif type == "warning":
        debug_container.warning(msg, icon="⚠️")
    else:
        debug_container.info(msg, icon="ℹ️")

def is_recent_strict(date_obj_or_str, source_name="Unknown"):
    """
    Vérifie si la date est < 7 jours.
    """
    now = datetime.now()
    article_date = None

    try:
        # Cas RSS (struct_time)
        if isinstance(date_obj_or_str, type(datetime.now().timetuple())):
            article_date = datetime.fromtimestamp(mktime(date_obj_or_str))
        
        # Cas String (ISO ou autre)
        elif isinstance(date_obj_or_str, str):
            try:
                article_date = datetime.fromisoformat(date_obj_or_str.replace("Z", "+00:00"))
            except:
                return True # Date inconnue => on garde

        if not article_date: return True 

        # Calcul delta
        if article_date.tzinfo is None:
            delta = now - article_date
        else:
            delta = now.astimezone() - article_date.astimezone()
            
        is_ok = delta.days <= 7
        # On ne logue pas chaque rejet pour ne pas spammer, sauf si nécessaire
        return is_ok
    except Exception as e:
        log_status(f"Date Error {source_name}: {e}", "warning")
        return True

# --- FETCHERS PANNEAUX 1 & 2 (RSS CLASSIQUE) ---

def fetch_rss_robust(feed_url, source_name, max_items):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_status(f"{source_name}: HTTP {response.status_code}", "error")
            return []
            
        feed = feedparser.parse(response.content)
        if not feed.entries: 
            log_status(f"{source_name}: Flux vide", "warning")
            return []

        valid_entries = []
        for e in feed.entries:
            if hasattr(e, 'published_parsed'):
                if not is_recent_strict(e.published_parsed, source_name):
                    continue
            
            clean_title = e.title.split(" - ")[0]
            summary = e.get("summary", e.get("description", ""))
            from bs4 import BeautifulSoup
            clean_summary = BeautifulSoup(summary, "html.parser").get_text()[:300] + "..."

            valid_entries.append({
                "source": source_name, 
                "title": clean_title, 
                "link": e.link, 
                "date": e.get("published", "")[:16],
                "summary": clean_summary
            })
            if len(valid_entries) >= max_items: break
            
        log_status(f"{source_name}: {len(valid_entries)} news récupérées", "success")
        return valid_entries
    except Exception as e:
        log_status(f"Err {source_name}: {str(e)[:30]}...", "error")
        return []

# --- FETCHERS PANNEAU 3 (ULTRA WIDE SCOPE + AI) ---

def fetch_batch_news(targets, batch_size=8):
    """
    Récupère les news brutes via RSS Google News par lots.
    """
    try:
        gn = GoogleNews(lang='fr', country='FR')
    except Exception as e:
        log_status(f"Init GoogleNews échoué: {e}", "error")
        return []
        
    raw_articles = []
    
    # Découpage en lots
    chunks = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    
    progress_bar = st.progress(0)
    
    for i, chunk in enumerate(chunks):
        progress_bar.progress((i + 1) / len(chunks))
        
        query_str = " OR ".join([f'"{company}"' for company in chunk])
        try:
            # 7d = 7 jours
            search = gn.search(query_str, when='7d')
            
            # Log détaillé du batch
            count = len(search.get('entries', []))
            if count > 0:
                log_status(f"Lot {i+1} : {count} résultats", "success")
            else:
                log_status(f"Lot {i+1} : 0 résultat", "info")

            for entry in search['entries']:
                raw_articles.append({
                    "title": entry.title,
                    "source": entry.source.title,
                    "published": entry.published,
                    "link": entry.link,
                    "snippet": entry.get('summary', '')[:200]
                })
            time.sleep(0.5) # Petite pause pour éviter le blocage
        except Exception as e:
            log_status(f"Err batch {i+1}: {e}", "error")

    progress_bar.empty()

    # Dédoublonnage
    df = pd.DataFrame(raw_articles)
    if not df.empty:
        df = df.drop_duplicates(subset=['link'])
        return df.to_dict(orient='records')
    
    log_status("Aucun article Google News trouvé au total", "warning")
    return []

def ai_strategic_filter(articles_list):
    """
    Utilise Gemini pour filtrer et trier le top 10 stratégique.
    """
    if not articles_list: return []
    
    log_status("Envoi à Gemini pour analyse...", "info")
    
    # Prompt optimisé
    prompt = f"""

Tu agis en tant que Directeur de la Stratégie. Voici des articles JSON bruts sur des ESN concurrentes.
    
    RÈGLES D'EXCLUSION STRICTES (Ce que je ne veux PAS) :
    - ❌ PAS de variations boursières ("Action en hausse", "Objectif de cours", "Dividende").
    - ❌ PAS de nominations mineures ou locales.
    - ❌ PAS de marketing/webinars.

    CRITÈRES DE SÉLECTION (Ce que je VEUX) :
    - ✅ M&A (Rachats, Fusions).
    - ✅ Contrats Stratégiques (Gros deals, Partenariats Cloud majeurs).
    - ✅ Offres Structurantes (Lancement division IA/Cyber).
    - ✅ Résultats Financiers Annuels/Trimestriels (Faits marquants uniquement).
    
    TA MISSION :
    1. Filtre sévèrement pour ne garder que le TOP 5-10 stratégique.
    2. Renvoie un JSON pur.

    Format item :
    {{
        "title": "Titre synthétique en français",
        "source": "Source",
        "date": "Date",
        "link": "Lien",
        "reason_for_selection": "Pourquoi c'est stratégique (pas de boursier)",
        "impact_level": "HIGH" ou "MEDIUM"
    }}

    DONNÉES :
    {json.dumps(articles_list)}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        parsed = json.loads(response.text)
        log_status(f"IA terminée : {len(parsed)} insights", "success")
        return parsed
    except Exception as e:
        log_status(f"AI Error: {e}", "error")
        return []

# ==============================================================================
# 3. INTERFACE
# ==============================================================================

def render_card(article, type="RSS"):
    if type == "RSS":
        st.markdown(f"""
        <div class="news-card">
            <div class="news-meta">
                <span>{article['source']}</span>
                <span>{article['date']}</span>
            </div>
            <div class="news-title"><a href="{article['link']}" target="_blank">{article['title']}</a></div>
            <div class="news-summary">{article['summary']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    elif type == "AI":
        # Adaptation du format IA au format Card
        impact = article.get('impact_level', 'HIGH') # Défaut HIGH car déjà filtré
        comment = article.get('reason_for_selection', 'Pas de détail.')
        
        # Gestion souple de la source (String ou Dict selon la provenance)
        src_name = article.get('source', 'Inconnu')
        if isinstance(src_name, dict): src_name = src_name.get('name', 'Inconnu')
        
        st.markdown(f"""
        <div class="news-card" style="border-left: 4px solid #D32F2F;">
            <div class="news-meta">
                <span>{src_name}</span>
                <span>{article.get('date', 'Récent')}</span>
            </div>
            <div class="news-title"><a href="{article['link']}" target="_blank">{article['title']}</a></div>
            <div class="ai-analysis">
                <span class="ai-badge badge-{impact}">{impact}</span>
                {comment}
            </div>
        </div>
        """, unsafe_allow_html=True)

def main():
    st.markdown("<h1 style='text-align: center;'>🛡️ Strat Watch V10</h1>", unsafe_allow_html=True)
    st.caption("Veille Stratégique | Focus Business & Finance | Ultra Wide Scope")
    
    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

    try:
        # --- 1. MACRO ECONOMIE ---
        st.markdown('<div class="section-header">🌍 1. Macro-Éco & Business</div>', unsafe_allow_html=True)
        with st.spinner("Chargement Macro..."):
            macro_news = []
            for feed in RSS_CONFIG["MACRO"]:
                macro_news.extend(fetch_rss_robust(feed["url"], feed["name"], max_items=4))
            if macro_news:
                for art in macro_news: render_card(art, "RSS")
            else:
                st.warning("⚠️ Aucune news Macro < 7j trouvée.")

        # --- 2. SECTEUR ---
        st.markdown('<div class="section-header">🏭 2. Industrie & Tech</div>', unsafe_allow_html=True)
        with st.spinner("Chargement Tech..."):
            sector_news = []
            for feed in RSS_CONFIG["SECTEUR"]:
                sector_news.extend(fetch_rss_robust(feed["url"], feed["name"], max_items=3))
            if sector_news:
                for art in sector_news: render_card(art, "RSS")
            else:
                st.info("Rien à signaler en sectoriel.")

        # --- 3. CONCURRENCE (NOUVEAU MOTEUR) ---
        st.markdown('<div class="section-header">⚔️ 3. Intelligence Concurrentielle (Ultra Wide)</div>', unsafe_allow_html=True)
        st.caption(f"Scope : {len(TARGETS_ESN)} Entreprises surveillées | Filtre : Gemini AI 2.0")

        # Fonction orchestratrice mise en cache pour éviter de re-scanner 50 boites
        # @st.cache_data(ttl=3600, show_spinner=False) CETTE LIGNE GENERE UN BUG SUR IPHONE
        def load_competition_v2():
            # 1. Récupération large (Muscle)
            raw_data = fetch_batch_news(TARGETS_ESN, batch_size=8)
            if not raw_data: return []
            
            # 2. Filtrage intelligent (Cerveau)
            curated_data = ai_strategic_filter(raw_data)
            return curated_data

        with st.spinner("Analyse approfondie en cours (Scan 50 ESN + AI Filtering)..."):
            comp_news = load_competition_v2()
            if comp_news:
                for art in comp_news:
                    render_card(art, "AI")
            else:
                st.success("✅ R.A.S. : Aucun signal faible stratégique détecté ce jour.")
                
    except Exception as e:
        st.error("Une erreur inattendue est survenue.")
        log_status(f"FATAL ERROR MAIN: {e}", "error")

if __name__ == "__main__":

    main()




