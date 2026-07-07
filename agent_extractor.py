import json
import requests
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup
# pyrefly: ignore [missing-import]
import pypdf
import os
import subprocess
import re

class BuybackAgentExtractor:
    def calculate_acceptance_ratio(self, buyback_size, buyback_price, small_shareholder_holding, participation):
        """Calculates the estimated retail acceptance ratio based on SEBI 15% reservation."""
        try:
            # Clean string inputs from the regex just in case (e.g., "10,80,00,000" -> 108000000.0)
            if isinstance(buyback_size, str):
                buyback_size = float(buyback_size.replace(',', '').replace('/-', '').replace('₹', '').strip())
            if isinstance(buyback_price, str):
                buyback_price = float(buyback_price.replace(',', '').replace('/-', '').replace('₹', '').strip())
            
            # Note: A true final ratio requires total outstanding shares. 
            # For this prototype, we will build a dynamic formula that reacts realistically to your sliders.
            # 15% SEBI Reservation base / (Retail Holding % * Participation %)
            base_reservation = 15.0 
            
            if small_shareholder_holding == 0 or participation == 0:
                return 0.0
                
            calculated_ratio = base_reservation / ((participation / 100.0) * small_shareholder_holding)
            
            # Cap it at 100% maximum acceptance
            return min(round(calculated_ratio, 2), 100.0)
            
        except Exception as e:
            return 0.0  # Fallback if data is missing or N/A

    def calculate_profitability(self, current_price, expected_post_price, buyback_price, acceptance_ratio):
        try:
            # If user didn't enter a post price, default to current market price to show conservative baseline
            post_price = float(expected_post_price) if expected_post_price else float(current_price)
            
            avg_realized = (float(buyback_price) * (float(acceptance_ratio) / 100.0)) + (post_price * (1.0 - (float(acceptance_ratio) / 100.0)))
            expected_profit = avg_realized - float(current_price)
            
            return round(expected_profit, 2), round(avg_realized, 2)
        except Exception:
            return 0.0, 0.0

    def __init__(self, schema_path: str = "schema.json"):
        self.schema_path = schema_path
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)
        
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        text = ""
        try:
            reader = pypdf.PdfReader(pdf_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return text

    def _extract_text_from_url(self, url: str) -> str:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup.get_text(separator='\n', strip=True)
        except Exception as e:
            print(f"Error fetching URL: {e}")
    def _parse_and_extract(self, raw_text: str):
        # Keyword-to-value mapping strategy
        clean_text = re.sub(r'\s+', ' ', raw_text)
        
        buyback_price = None
        record_date = None
        offer_type = None
        buyback_size = None 
        
        # Keyword: Buyback Price / Price
        price_match = re.search(r'(?:buyback\s*price\s*of|at\s*a\s*price\s*of|not\s*exceeding).{0,25}?(?:rs\.?|inr|\u20b9|rupees)\s*([\d,]+(?:\.\d+)?)', clean_text, re.IGNORECASE)
        
        if not price_match:
            for m in re.finditer(r'(?:price).{0,25}?(?:rs\.?|inr|\u20b9|rupees)\s*([\d,]+(?:\.\d+)?)', clean_text, re.IGNORECASE):
                start = max(0, m.start() - 40)
                context = clean_text[start:m.start()].lower()
                if "face value" not in context and "market" not in context:
                    price_match = m
                    break

        if price_match:
            try:
                buyback_price = float(price_match.group(1).replace(',', ''))
            except ValueError:
                buyback_price = price_match.group(1).strip()
        else:
            print("Keyword 'Price' not found in document.")

        # Check for Amended/Revised Buyback Price (Overrides base price)
        amended_price_pattern = re.compile(r'(?:increased\s+from.*?to|revised\s+to|revised\s+buyback\s+price\s+of)\s*(?:rs\.?|inr|\u20b9|rupees)?\s*([\d,]+(?:\.\d+)?)', re.IGNORECASE)
        amended_match = amended_price_pattern.search(clean_text)
        if amended_match:
            try:
                buyback_price = float(amended_match.group(1).replace(',', ''))
            except ValueError:
                buyback_price = amended_match.group(1).strip()

        # Keyword: Record Date
        date_match = re.search(r'record\s*date.*?(?:is\s*|on\s*|:\s*)?([a-zA-Z]+\s+\d{1,2}[\,\s]+20\d{2}|\d{1,2}[\/\-]\d{1,2}[\/\-]20\d{2})', clean_text, re.IGNORECASE)
        if date_match:
            record_date = date_match.group(1).strip()
        else:
            print("Keyword 'Record Date' not found in document.")
            
        # Keyword: Offer Type (Scoring System)
        tender_indicators = ["tender offer", "proportionate basis", "through the tender offer", "buyback regulations"]
        tender_score = sum(1 for indicator in tender_indicators if re.search(indicator, clean_text[:15000], re.IGNORECASE))
        
        if tender_score >= 2:
            offer_type = "Tender Offer"
        elif re.search(r'open\s*market', clean_text[:15000], re.IGNORECASE):
            offer_type = "Open Market"
        else:
            offer_type = "Unknown"
            print("Method detection failed. Checking Page 1-3 content for tender offer terminology.")
            
        # Buyback Size (just keeping the existing regex as fallback)
        size_pattern = re.compile(r'(?:aggregate\s*amount\s*(?:of\s*the\s*buyback\s*)?(?:shall|will|does)?\s*not\s*exceed(?:ing)?|aggregate\s*amount\s*of\s*up\s*to|maximum\s*buyback\s*size\s*(?:of)?|total\s*outlay\s*of|size\s*of\s*(?:the\s*)?buyback\s*(?:is\s*)?)\s*(?:Rs\.?|INR|\u20b9|Rupees)?\s*([\d,]+(?:\.\d+)?)(?:/-)?\s*(Crores?|Cr\.?|Lakhs?|Millions?)?', re.IGNORECASE)
        for match in size_pattern.finditer(clean_text):
            val_str = match.group(1).strip()
            unit = match.group(2).lower() if match.group(2) else ""
            if unit:
                try:
                    val = float(val_str.replace(',', ''))
                    if 'lakh' in unit:
                        val = val / 100.0
                    elif 'million' in unit:
                        val = val / 10.0
                    buyback_size = round(val, 2)
                    break
                except ValueError:
                    buyback_size = val_str
                    break
            else:
                buyback_size = val_str
                break
                
        if not buyback_size:
            print("Keyword 'Buyback Size' not found in document.")

        structured_data = {
            "buyback_size": buyback_size,
            "buyback_price": buyback_price,
            "record_date": record_date,
            "offer_type": offer_type
        }
        return structured_data, raw_text
    def parse_announcement(self, pdf_path: str):
        """Extracts buyback details from the Announcement PDF document."""
        raw_text = self._extract_text_from_pdf(pdf_path)
        if not raw_text:
            return {"error": "Could not extract text from PDF"}, ""
        
        # Capture whatever the parsing function returns
        result = self._parse_and_extract(raw_text)
        
        # Defensive check: unwrap the dictionary safely
        if isinstance(result, tuple):
            # If the AI put the dictionary in the first slot, just grab it!
            if len(result) > 0 and isinstance(result[0], dict):
                structured_data = result[0]
            else:
                # Otherwise, build it manually
                structured_data = {
                    "buyback_size": result[0] if len(result) > 0 else None,
                    "buyback_price": result[1] if len(result) > 1 else None,
                    "record_date": result[2] if len(result) > 2 else None,
                    "offer_type": result[3] if len(result) > 3 else None,
                    "acceptance_rate_percentage": result[4] if len(result) > 4 else None,
                    "small_shareholder_percentage": result[5] if len(result) > 5 else None
                }
        else:
            structured_data = result if isinstance(result, dict) else {}
            
        return structured_data, raw_text

    def get_shareholding_percentage(self, pdf_path, company_name, cmp_price=0.0):
        """
        Strict extraction for retail (small shareholder) percentage.
        Enforces strict document validation and ONLY extracts from the 
        Category of Shareholder table.
        """
        raw_text = self._extract_text_from_pdf(pdf_path)
        
        if not raw_text:
            print("PDF is empty / unreadable. Triggering online fallback.")
            return self.fetch_shareholding_online(company_name), ""
            
        # 1. Strict Document Validation (Fail Fast)
        text_lower = raw_text.lower()
        
        # Rule 3: Fail immediately if it's an announcement instead of an SHP
        if "public announcement" in text_lower[:2000] or "letter of offer" in text_lower[:2000]:
            if "category of shareholder" not in text_lower:
                print("VALIDATION FAILED: This is an Announcement/Notice, NOT an SHP document.")
                return self.fetch_shareholding_online(company_name), raw_text
                
        if "shareholding pattern" not in text_lower and "category of shareholder" not in text_lower:
            print("VALIDATION FAILED: This does not appear to be an SHP document.")
            return self.fetch_shareholding_online(company_name), raw_text
        
        print(f"\n{'='*60}")
        print(f"STRICT SHP EXTRACTION for '{company_name}'")
        print(f"CMP = Rs. {cmp_price}")
        print(f"{'='*60}")
        
        # =======================================================
        # STRICT EXTRACTION: Direct "Category of Shareholders" table
        # =======================================================
        print("\nSearching for 'Individuals up to Rs.2 lakhs' row in Category table...")
        
        extracted_value = self._tier1_category_table(raw_text)
        
        # 3. Handle the 'NOT_FOUND' Response
        if extracted_value == 'NOT_FOUND' or extracted_value is None:
            print("LLM/Regex confirms data is missing or NOT_FOUND. Triggering online search...")
            fallback_data = self.fetch_shareholding_online(company_name)
            return fallback_data, raw_text
            
        print(f"[SUCCESS] Extracted retail holding = {extracted_value}%")
        return {"retail_holding_percentage": extracted_value, "is_approximate": False, "source": "PDF (SHP Table)"}, raw_text

    # -----------------------------------------------------------
    # TIER 1 HELPER: Category of Shareholders table
    # -----------------------------------------------------------
    def _tier1_category_table(self, raw_text):
        """
        Specialized extraction for 'Small Shareholder' data (defined as 
        'Individuals holding nominal share capital up to Rs. 2 lakhs') from an SHP.
        Uses a scoped regex with DOTALL to handle multi-line table rows.
        """
        # Target string: "Individuals holding nominal share capital up to Rs. 2 lakhs"
        # We allow "1" or "2" lakhs, and "up to" or "upto".
        pattern = r"Individuals holding nominal share capital\s+up\s*to\s*(?:Rs\.?)?\s*(?:1|2)\s*lakhs?.*?(?:\d+\,?\d*\,?\d*)\s*(\d+\.\d+)"
        
        match = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)
        
        if match:
            extracted_value = match.group(1)
            val = float(extracted_value)
            # Ensure it is a reasonable retail percentage (not 100%)
            if 0.1 <= val <= 50.0:
                print(f"  -> Successfully extracted Small Shareholder percentage: {val}%")
                return val
            else:
                print(f"  -> Extracted {val}%, but it falls outside valid retail range (0.1 - 50.0%).")
        
        print("  -> Small Shareholder data not found in primary table using strict regex.")
        return None

    # -----------------------------------------------------------
    # TIER 2 HELPER: Distribution of Shareholding table
    # -----------------------------------------------------------
    def _tier2_distribution_table(self, raw_text, cmp_price):
        """
        Parses the 'Distribution of Shareholding' table.
        These tables have share-count brackets like:
            1 - 500       | 12345 | 6789012 | 45.23
            501 - 1000    | 2345  | 1234567 | 12.45
            ...
        We calculate max_retail_shares = ₹2,00,000 / CMP, then sum 
        the "% of total shares" for all brackets where the upper bound
        is <= max_retail_shares.
        """
        max_retail_shares = int(200000 / cmp_price)
        print(f"  -> Max retail shares at CMP Rs. {cmp_price} = {max_retail_shares} shares")
        
        # Find the Distribution of Shareholding section
        lines = raw_text.split('\n')
        in_distribution_section = False
        bracket_rows = []
        
        # Pattern to match share-count brackets like "1 - 500", "501 to 1000", "5001 and above"
        bracket_pattern = re.compile(
            r'(\d[\d,]*)\s*(?:[-–to]+|and\s*above|above)\s*(\d[\d,]*)?'
        )
        
        for line in lines:
            ll = line.lower()
            
            # Detect section start
            if 'distribution of share' in ll or 'distribution of equity share' in ll:
                in_distribution_section = True
                print(f"  -> Found 'Distribution of Shareholding' section header.")
                continue
            
            # Detect section end (next major header)
            if in_distribution_section and ('category of share' in ll or 'promoter' in ll and 'holding' in ll):
                break
                
            if in_distribution_section:
                # Try to parse a bracket row
                m = bracket_pattern.search(line)
                if m:
                    try:
                        lower = int(m.group(1).replace(',', ''))
                        upper_str = m.group(2)
                        upper = int(upper_str.replace(',', '')) if upper_str else 999999999
                        
                        # Extract all percentage-like numbers from this line
                        all_nums = re.findall(r'(\d{1,3}\.\d{1,4})', line)
                        pct_vals = [float(n) for n in all_nums if 0.01 <= float(n) <= 100.0]
                        
                        if pct_vals:
                            # The last percentage in the row is typically "% of total shares"
                            pct = pct_vals[-1]
                            bracket_rows.append({
                                'lower': lower, 'upper': upper,
                                'pct': pct, 'raw': line.strip()[:60]
                            })
                    except (ValueError, TypeError):
                        pass
        
        if not bracket_rows:
            print("  -> No bracket rows found in Distribution table.")
            return None
            
        print(f"  -> Found {len(bracket_rows)} bracket rows:")
        
        # Sum all brackets where the upper bound <= max_retail_shares
        retail_total = 0.0
        for row in bracket_rows:
            included = row['lower'] <= max_retail_shares
            marker = "[YES]" if included else "[NO ]"
            print(f"     {marker} [{row['lower']:>7,} - {row['upper']:>7,}] -> {row['pct']:.2f}%")
            if included:
                retail_total += row['pct']
        
        retail_total = round(retail_total, 2)
        
        # Sanity check
        if retail_total < 2.0:
            print(f"  -> WARNING: Summed retail % = {retail_total}% seems too low. Rejecting.")
            return None
        if retail_total > 60.0:
            print(f"  -> WARNING: Summed retail % = {retail_total}% seems too high. Rejecting.")
            return None
            
        return retail_total

    def fetch_shareholding_online(self, company_name: str):
        """Multi-source web scraper for retail shareholding percentage.
        Uses a search-first approach to resolve correct URL slugs."""
        print(f"\n{'='*60}")
        print(f"Initiating online search for {company_name}...")
        print(f"{'='*60}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        result_percentage = None
        short_name = company_name.split()[0].strip()  # e.g. "Jagsonpal"
        
        # -------------------------------------------------------
        # SOURCE 1: screener.in (search-first to resolve slug)
        # -------------------------------------------------------
        try:
            print(f"\n[SOURCE 1] Trying screener.in search for '{short_name}'...")
            search_url = f"https://www.screener.in/api/company/search/?q={short_name}"
            print(f"  -> Search API: {search_url}")
            resp = requests.get(search_url, headers=headers, timeout=8)
            
            if resp.status_code == 200:
                results = resp.json()
                if results and len(results) > 0:
                    # First result is usually the best match
                    slug = results[0].get('url', '')
                    company_url = f"https://www.screener.in{slug}"
                    print(f"  -> Resolved to: {company_url}")
                    
                    page_resp = requests.get(company_url, headers=headers, timeout=8)
                    if page_resp.status_code == 200:
                        soup = BeautifulSoup(page_resp.text, 'html.parser')
                        page_text = soup.get_text().lower()
                        
                        patterns = [
                            r'(?:individual.*?up\s*to.*?(?:1|2)\s*lakh).*?(\d{1,2}\.\d{1,2})\s*%',
                            r'public[:\s]+(\d{1,2}\.\d{1,2})\s*%',
                            r'retail[:\s]+(\d{1,2}\.\d{1,2})\s*%',
                            r'public\s*shareholding.*?(\d{1,2}\.\d{1,2})',
                        ]
                        for pat in patterns:
                            m = re.search(pat, page_text)
                            if m:
                                val = float(m.group(1))
                                if 5.0 <= val <= 50.0:
                                    result_percentage = val
                                    print(f"  -> MATCH: Found {result_percentage}% via screener.in")
                                    break
                        if result_percentage is None:
                            print(f"  -> Page loaded but no matching percentage found.")
                    else:
                        print(f"  -> Company page returned HTTP {page_resp.status_code}")
                else:
                    print(f"  -> No search results returned for '{short_name}'")
            else:
                print(f"  -> Search API returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"  -> screener.in FAILED: {e}")
        
        # -------------------------------------------------------
        # SOURCE 2: Trendlyne (search-first)
        # -------------------------------------------------------
        if result_percentage is None:
            try:
                print(f"\n[SOURCE 2] Trying Trendlyne for '{short_name}'...")
                trendlyne_search = f"https://trendlyne.com/eq/search/{short_name}/"
                print(f"  -> URL: {trendlyne_search}")
                resp = requests.get(trendlyne_search, headers=headers, timeout=8, allow_redirects=True)
                
                if resp.status_code == 200:
                    page_text = resp.text.lower()
                    # Look for the shareholding data on the page
                    patterns = [
                        r'individual.*?up\s*to.*?(\d{1,2}\.\d{1,2})\s*%',
                        r'(?:public|retail)\s*(?:shareholding|holding).*?(\d{1,2}\.\d{1,2})\s*%',
                        r'(?:public|retail|individual).*?(\d{1,2}\.\d{1,2})%',
                    ]
                    for pat in patterns:
                        m = re.search(pat, page_text)
                        if m:
                            val = float(m.group(1))
                            if 5.0 <= val <= 50.0:
                                result_percentage = val
                                print(f"  -> MATCH: Found {result_percentage}% from Trendlyne")
                                break
                    if result_percentage is None:
                        print(f"  -> No matching percentage on Trendlyne page.")
                else:
                    print(f"  -> Trendlyne returned HTTP {resp.status_code}")
            except Exception as e:
                print(f"  -> Trendlyne FAILED: {e}")
        
        # -------------------------------------------------------
        # SOURCE 3: Google search (most reliable search engine)
        # -------------------------------------------------------
        if result_percentage is None:
            try:
                print(f"\n[SOURCE 3] Trying Google search for '{company_name}'...")
                query = f"{company_name} individual shareholding up to 2 lakhs percentage"
                google_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
                print(f"  -> Query: {query}")
                
                google_headers = {**headers, 'Accept': 'text/html'}
                resp = requests.get(google_url, headers=google_headers, timeout=8)
                
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    text_to_search = soup.get_text().lower()
                    print(f"  -> Scraped {len(text_to_search)} chars from Google results")
                    
                    # Extract floats near shareholding keywords
                    patterns = [
                        r'up\s*to\s*(?:rs\.?\s*)?(?:1|2)\s*lakh.*?(\d{1,2}\.\d{1,2})\s*%',
                        r'(?:public|retail|individual).*?(\d{1,2}\.\d{1,2})\s*%',
                    ]
                    for pat in patterns:
                        m = re.search(pat, text_to_search)
                        if m:
                            val = float(m.group(1))
                            if 5.0 <= val <= 50.0:
                                result_percentage = val
                                print(f"  -> MATCH: Found {result_percentage}% from Google snippets")
                                break
                    
                    # Broader fallback
                    if result_percentage is None:
                        pcts = re.findall(r'(\d{1,2}\.\d{1,2})\s*%', text_to_search)
                        valid = [float(p) for p in pcts if 5.0 <= float(p) <= 50.0]
                        if valid:
                            result_percentage = valid[0]
                            print(f"  -> BROAD MATCH: Found {result_percentage}% from Google (generic)")
                        else:
                            print(f"  -> No valid percentages found in Google results")
                else:
                    print(f"  -> Google returned HTTP {resp.status_code}")
            except Exception as e:
                print(f"  -> Google search FAILED: {e}")
        
        # -------------------------------------------------------
        # SOURCE 4: choiceindia.com (direct company name support)
        # -------------------------------------------------------
        if result_percentage is None:
            try:
                print(f"\n[SOURCE 4] Trying choiceindia.com for '{short_name}'...")
                choice_url = f"https://www.choiceindia.com/stocks/search?q={short_name}"
                print(f"  -> URL: {choice_url}")
                resp = requests.get(choice_url, headers=headers, timeout=8, allow_redirects=True)
                
                if resp.status_code == 200:
                    page_text = resp.text.lower()
                    m = re.search(r'(?:public|retail|individual).*?(\d{1,2}\.\d{1,2})%', page_text)
                    if m:
                        val = float(m.group(1))
                        if 5.0 <= val <= 50.0:
                            result_percentage = val
                            print(f"  -> MATCH: Found {result_percentage}% from ChoiceIndia")
                else:
                    print(f"  -> ChoiceIndia returned HTTP {resp.status_code}")
            except Exception as e:
                print(f"  -> ChoiceIndia FAILED: {e}")
        
        # -------------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------------
        print(f"\n{'='*60}")
        if result_percentage is not None:
            print(f"Online search found: {result_percentage}%")
            print(f"{'='*60}\n")
            return {
                "retail_holding_percentage": result_percentage,
                "is_approximate": True,
                "source": "Online"
            }
        else:
            print("WEB SEARCH FAILED: Could not find retail percentage online.")
            print("Returning conservative baseline of 15.0%")
            print(f"{'='*60}\n")
            return {
                "retail_holding_percentage": 15.0,
                "is_approximate": True,
                "source": "Online (Baseline)"
            }