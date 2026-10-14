# Vendor_agreement.py - Updated code

import os
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime, timedelta
import re
from typing import Dict, Tuple

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class DocumentGenerator:
    def __init__(self):
        self.today = datetime.now().strftime("%B %d, %Y")
        self.one_year_later = (datetime.now() + timedelta(days=365)).strftime("%B %d, %Y")
        self.contract_id = f"CTR-{datetime.now().year}-{datetime.now().month:02d}{datetime.now().day:02d}"
        self.parsed_prompt = {}
        self.generated_content_history = []  

    def _placeholder(self, label: str) -> str:
        """Generate consistent editable placeholder"""
        return f"[{label.upper()}]"

    def _call_groq(self, prompt: str) -> str:
        """Helper function to call Groq API with consistent parameters"""
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content.strip()

    def _clean_content(self, content: str) -> str:
        """Clean content by removing markdown formatting and unwanted symbols"""
        content = re.sub(r'\*\*|\*|#|_', '', content)
        content = re.sub(r'\[.*?BLOCK (START|END)\]', '', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        return content.strip()

    def _generate_dynamic_content(self, section_name, default_template, contract_type, context_summary=""):
        """Generate content with strict section formatting"""
        vendor = self.parsed_prompt.get("supplier_name", "")
        product = self.parsed_prompt.get("product", "")
        price = self.parsed_prompt.get("price", "")
        address = self.parsed_prompt.get("delivery", "[DELIVERY ADDRESS]")
        
        # Create context awareness
        previous_content = "\n".join(self.generated_content_history[-3:]) if self.generated_content_history else ""
        
        prompt = f"""
        Generate ONLY the {section_name} section for a {contract_type} contract.
        
        **CONTRACT OVERVIEW:**
        - Vendor: {vendor}
        - Product/Service: {product}
        - Price: {price}
        - Delivery Address: {address}
        
        **CONTEXT FROM PREVIOUS SECTIONS (DO NOT REPEAT THIS VERBATIM):**
        {previous_content}
        
        **SECTION-SPECIFIC FOCUS:**
        {self._get_section_focus(section_name)}
        
        **REQUIRED FORMAT - FOLLOW EXACTLY:**
        **{section_name}**
        • [First bullet point - focus on NEW information specific to this section]
        • [Second bullet point - avoid repeating details from other sections]
        • [Third bullet point - add unique aspects relevant to {section_name}]
        • [Fourth bullet point - if applicable, ensure it's distinct]
        
        **CRITICAL INSTRUCTIONS:**
        - Start with **{section_name}** on its own line
        - Use bullet points with • symbol only
        - Each bullet should be 1 line maximum
        - DO NOT repeat information that's already covered in previous sections
        - Focus on unique aspects specific to {section_name}
        - If you must reference previous info, do it briefly and add new context
        - Return ONLY the section content in the exact format above
        """
        
        try:
            dynamic_content = self._call_groq(prompt)
            dynamic_content = re.sub(r'\n\s*\n', '\n\n', dynamic_content)
            
            if dynamic_content and len(dynamic_content.strip()) > 10:
                # Add to history to avoid repetition in future sections
                self.generated_content_history.append(f"{section_name}: {dynamic_content}")
                return dynamic_content.strip()
            else:
                print(f"LLM returned empty content for {section_name}, using default template")
                return default_template
        except Exception as e:
            print(f"Error generating dynamic content for {section_name}: {e}")
            return default_template

    def _get_section_focus(self, section_name: str) -> str:
        """Provide section-specific guidance to avoid repetition"""
        focus_guides = {
            "SCOPE OF AGREEMENT": "Focus on WHAT is being supplied/provided - the core deliverables and objectives.",
            "COMMERCIAL TERMS": "Focus on PRICING, PAYMENT TERMS, and FINANCIAL arrangements only.",
            "DELIVERY TERMS": "Focus on DELIVERY SCHEDULE, LOCATION, TRANSPORTATION, and TIMING.",
            "QUALITY ASSURANCE": "Focus on QUALITY STANDARDS, INSPECTIONS, TESTING, and ACCEPTANCE CRITERIA.",
            "PENALTIES AND LIABILITIES": "Focus on CONSEQUENCES, DAMAGES, INSURANCE, and LIABILITY LIMITATIONS.",
            "CONFIDENTIALITY": "Focus on INFORMATION PROTECTION, NON-DISCLOSURE, and DATA SECURITY.",
            "FORCE MAJEURE": "Focus on UNFORESEEN EVENTS, EXCUSABLE DELAYS, and CONTRACT SUSPENSION.",
            "TERMINATION": "Focus on ENDING THE CONTRACT, NOTICE PERIODS, and POST-TERMINATION OBLIGATIONS.",
            "DISPUTE RESOLUTION": "Focus on CONFLICT RESOLUTION METHODS, JURISDICTION, and LEGAL PROCESSES.",
            "DIGITAL SIGNATURES": "Focus on ELECTRONIC EXECUTION, LEGAL VALIDITY, and SIGNATURE PROCESS."
        }
        return focus_guides.get(section_name, "Provide specific terms relevant to this section.")

    
    def _parse_user_prompt(self, vendor, contract_title, start_date, end_date, 
                        details, rfq_po, contract_type, price_type=None):
        """Parse all fields from user inputs; insert editable placeholders if absent."""
        
        # Handle rfq_po which can be a string or dict
        po_reference = ""
        if isinstance(rfq_po, dict):
            po_reference = rfq_po.get('title', rfq_po.get('id', "[PO REFERENCE]"))
        else:
            po_reference = rfq_po or "[PO REFERENCE]"
        
        return {
            "buyer_name": self._placeholder("buyer name"),
            "supplier_name": vendor or self._placeholder("supplier name"),
            "contract_title": contract_title or self._placeholder("contract title"),
            "start_date": start_date or self.today,
            "end_date": end_date or self.one_year_later,
            "product": details or self._placeholder("product/service description"),
            "po_reference": po_reference,
            "price": price_type or self._placeholder("pricing details"),
            "payment_terms": "Net 30 days",
            "effective_date": start_date or self.today,
            "delivery": self._placeholder("delivery schedule and address"),
            "quality_standards": "Industry standard quality requirements",
            "contract_type": contract_type or "General"
        }

    # Block generation functions
    def _generate_title_block(self) -> str:
        """Generate title block with dynamic title"""
        title = self.parsed_prompt.get("contract_title", "Vendor Supply Agreement")
        return f"{title}"

    def _generate_contract_id(self) -> str:
        """Generate contract details section"""
        start_date = self.parsed_prompt.get("start_date", self.today)
        end_date = self.parsed_prompt.get("end_date", self.one_year_later)
        return (
            f"Contract ID: {self.contract_id}\n"
            f"Effective Date: {start_date}\n"
            f"End Date: {end_date}\n"
        )
    
    def _generate_parties_intro(self) -> str:
        """Generate parties introduction"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        product = self.parsed_prompt.get("product", "")
        
        intro_text = "This Agreement is made between:"
        
        if "service" in contract_type.lower():
            intro_text = "This Service Agreement is made between:"
        elif "supply" in contract_type.lower():
            intro_text = "This Supply Agreement is made between:"
        elif "maintenance" in contract_type.lower():
            intro_text = "This Maintenance Agreement is made between:"
            
        # Add context-specific introduction
        if product:
            intro_text += f"\n\nThe parties identified below, intending to be legally bound, agree to the following terms and conditions for the {contract_type or 'supply'} of {product}."
        else:
            intro_text += f"\n\nThe parties identified below, intending to be legally bound, agree to the following terms and conditions."
        
        return intro_text

    def _generate_buyer_block(self) -> str:
        name = self.parsed_prompt.get("buyer_name", self._placeholder("buyer name"))
        address = self._placeholder("buyer address")
        rep = self._placeholder("buyer representative")
        return (
            f"**BUYER:**\n"
            f"Enterprise Name: {name}\n"
            f"Address: {address}\n"
            f"Authorized Representative: {rep}\n"
        )

    def _generate_supplier_block(self) -> str:
        name = self.parsed_prompt.get("supplier_name", self._placeholder("supplier name"))
        address = self._placeholder("supplier address")
        rep = self._placeholder("supplier representative")
        return (
            f"**SUPPLIER:**\n"
            f"Vendor Name: {name}\n"
            f"Address: {address}\n"
            f"Authorized Representative: {rep}\n"
        )

    def _generate_scope_block(self):
        """Generate scope block - comprehensive but not repetitive"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        product = self.parsed_prompt.get("product", "[PRODUCT/SERVICE DESCRIPTION]")
        
        # Reset history at the start of document generation
        if not self.generated_content_history:
            self.generated_content_history = []
        
        dynamic_content = self._generate_dynamic_content(
            "SCOPE OF AGREEMENT",
            f"**SCOPE OF AGREEMENT**\n• Supplier agrees to provide {product}\n• All specifications as per agreed requirements\n• Quality standards must be maintained\n• Delivery as per agreed schedule",
            contract_type
        )
        
        return dynamic_content

    def _generate_commercial_block(self):
        """Generate commercial terms - focus on financial aspects only"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        price = self.parsed_prompt.get("price", "[PRICING DETAILS]")
        
        dynamic_content = self._generate_dynamic_content(
            "COMMERCIAL TERMS",
            f"**COMMERCIAL TERMS**\n• Total Order Value: {price}\n• Payment Terms: Net 30 days\n• Price Validity: Fixed for contract period\n• Taxes: Applicable as per regulations",
            contract_type
        )
        
        return dynamic_content

    def _generate_delivery_block(self):
        """Generate delivery terms - focus on logistics only"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        delivery_info = self.parsed_prompt.get("delivery", "[DELIVERY SCHEDULE AND ADDRESS]")
        
        dynamic_content = self._generate_dynamic_content(
            "DELIVERY TERMS",
            f"**DELIVERY TERMS**\n• Delivery Schedule: {delivery_info}\n• Address: [SPECIFY ADDRESS]\n• Inspection upon delivery required",
            contract_type
        )
        
        return dynamic_content

    def _generate_quality_block(self):
        """Generate quality assurance - focus on standards only"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        standards = self.parsed_prompt.get("quality_standards", "Industry standard quality requirements")
        
        dynamic_content = self._generate_dynamic_content(
            "QUALITY ASSURANCE",
            f"**QUALITY ASSURANCE**\n• Supplier must adhere to {standards}\n• Buyer reserves right to conduct inspections\n• Rejection criteria and process defined",
            contract_type
        )
        
        return dynamic_content

    def _generate_penalties_block(self):
        """Generate penalties block - focus on consequences only"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "PENALTIES AND LIABILITIES",
            "**PENALTIES AND LIABILITIES**\n• Late delivery penalties specified\n• Quality breach consequences outlined\n• Insurance requirements defined\n• Liability limitations stated",
            contract_type
        )
        
        return dynamic_content

    def _generate_confidentiality_block(self):
        """Generate confidentiality block - focus on information protection"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "CONFIDENTIALITY",
            "**CONFIDENTIALITY**\n• Both parties agree to maintain confidentiality\n• No disclosure to third parties without consent\n• Obligation survives termination",
            contract_type
        )
        
        return dynamic_content

    def _generate_force_majeure_block(self):
        """Generate force majeure block - focus on unforeseen events"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "FORCE MAJEURE",
            "**FORCE MAJEURE**\n• Neither party liable for events beyond reasonable control\n• Natural disasters, wars, government actions excluded\n• Affected party must notify promptly",
            contract_type
        )
        
        return dynamic_content

    def _generate_termination_block(self):
        """Generate termination clause - focus on ending the contract"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "TERMINATION",
            "**TERMINATION**\n• Either party may terminate with 30 days written notice\n• Immediate termination for material breach\n• Payments due upon termination",
            contract_type
        )
        
        return dynamic_content

    def _generate_dispute_resolution_block(self):
        """Generate dispute resolution clause - focus on conflict resolution"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "DISPUTE RESOLUTION",
            "**DISPUTE RESOLUTION**\n• Disputes resolved through negotiation first\n• Mediation by neutral third party if needed\n• Governing laws of jurisdiction apply",
            contract_type
        )
        
        return dynamic_content

    def _generate_digital_signatures_block(self):
        """Generate digital signatures clause - focus on execution"""
        contract_type = self.parsed_prompt.get("contract_type", "")
        
        dynamic_content = self._generate_dynamic_content(
            "DIGITAL SIGNATURES",
            "**DIGITAL SIGNATURES**\n• Agreement may be executed electronically\n• Digital signatures legally binding\n• Equivalent to handwritten signatures",
            contract_type
        )
        
        return dynamic_content

    def generate_agreement(self, vendor, contract_title, start_date, end_date, 
                      details, rfq_po, contract_type, price_type=None, procurement_data=None):
        """
        Generate complete agreement from individual parameters
        Returns structured blocks of the agreement with clean formatting
        """
        # Reset history for each new agreement generation
        self.generated_content_history = []
        
        # Parse the parameters to extract structured data
        self.parsed_prompt = self._parse_user_prompt(
            vendor, contract_title, start_date, end_date, 
            details, rfq_po, contract_type, price_type
        )
        
        # Enhance parsed prompt with procurement data if available
        if procurement_data:
            self._enhance_with_procurement_data(procurement_data)
        
        # Generate each block with its dedicated function
        generated_content = "\n\n".join([
            self._generate_title_block(),
            self._generate_contract_id(),
            self._generate_parties_intro(),
            self._generate_buyer_block(),
            self._generate_supplier_block(),
            self._generate_scope_block(),
            self._generate_commercial_block(),
            self._generate_delivery_block(),
            self._generate_quality_block(),
            self._generate_penalties_block(),
            self._generate_confidentiality_block(),
            self._generate_force_majeure_block(),
            self._generate_termination_block(),
            self._generate_dispute_resolution_block(),
            self._generate_digital_signatures_block()
        ])
        
        # Clean the content and parse into structured blocks
        cleaned_content = self._clean_content(generated_content)
        return self._parse_to_blocks(cleaned_content)

    def _enhance_with_procurement_data(self, procurement_data):
        """Enhance the parsed prompt with procurement data"""
        # Map procurement data to relevant fields
        if procurement_data.get('product_specification'):
            self.parsed_prompt['product'] = procurement_data['product_specification']
        
        if procurement_data.get('quantity') and procurement_data.get('unit'):
            self.parsed_prompt['quantity'] = f"{procurement_data['quantity']} {procurement_data['unit']}"
        
        if procurement_data.get('budget') and procurement_data.get('currency'):
            currency_symbols = {'usd': '$', 'eur': '€', 'gbp': '£'}
            symbol = currency_symbols.get(procurement_data['currency'].lower(), procurement_data['currency'].upper())
            self.parsed_prompt['price'] = f"{symbol}{procurement_data['budget']}"
        
        if procurement_data.get('delivery_date'):
            self.parsed_prompt['delivery'] = f"Delivery by {procurement_data['delivery_date']}"
        
        if procurement_data.get('vendor'):
            self.parsed_prompt['supplier_name'] = procurement_data['vendor']
    def _parse_to_blocks(self, content: str) -> Dict[str, str]:
        """
        Parse generated content into structured blocks with improved section detection
        """
        blocks = {
            'title': '',
            'contract_id': '',
            'parties_intro': '',
            'buyer': '',
            'supplier': '',
            'scope': '',
            'commercial': '',
            'delivery': '',
            'quality': '',
            'penalties': '',
            'confidentiality': '',
            'force_majeure': '',
            'termination': '',
            'dispute_resolution': '',
            'digital_signatures': ''
        }
        
        # Split content into sections using double newlines as separators
        sections = content.split('\n\n')
        
        current_section = None
        current_content = []
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            lines = section.split('\n')
            first_line = lines[0].strip().lower()
            
            # Detect section type based on first line
            if 'contract id:' in first_line:
                current_section = 'contract_id'
                current_content = lines
            elif any(phrase in first_line for phrase in ['this agreement', 'this service agreement', 'this supply agreement', 'this maintenance agreement']):
                current_section = 'parties_intro'
                current_content = lines
            elif first_line.startswith('buyer:'):
                current_section = 'buyer'
                current_content = lines
            elif first_line.startswith('supplier:'):
                current_section = 'supplier'
                current_content = lines
            elif 'scope of agreement' in first_line:
                current_section = 'scope'
                current_content = lines
            elif 'commercial terms' in first_line:
                current_section = 'commercial'
                current_content = lines
            elif 'delivery terms' in first_line:
                current_section = 'delivery'
                current_content = lines
            elif 'quality assurance' in first_line:
                current_section = 'quality'
                current_content = lines
            elif any(term in first_line for term in ['penalties and liabilities', 'penalties & liabilities', 'penalties']):
                current_section = 'penalties'
                current_content = lines
            elif 'confidentiality' in first_line:
                current_section = 'confidentiality'
                current_content = lines
            elif 'force majeure' in first_line:
                current_section = 'force_majeure'
                current_content = lines
            elif 'termination' in first_line:
                current_section = 'termination'
                current_content = lines
            elif 'dispute resolution' in first_line:
                current_section = 'dispute_resolution'
                current_content = lines
            elif 'digital signatures' in first_line:
                current_section = 'digital_signatures'
                current_content = lines
            else:
                # If we're in a section, add to current content
                if current_section:
                    current_content.extend(lines)
                else:
                    # This is likely the title section
                    if not blocks['title']:
                        blocks['title'] = section
                    else:
                        blocks['title'] += '\n\n' + section
                continue
            
            # Save the previous section if it exists
            if current_section and current_content:
                blocks[current_section] = '\n'.join(current_content).strip()
        
        # Don't forget the last section
        if current_section and current_content:
            blocks[current_section] = '\n'.join(current_content).strip()
        
        # Check if we need to manually extract missing sections from the penalties block
        # (since the LLM sometimes combines multiple sections)
        penalties_content = blocks.get('penalties', '')
        if penalties_content and 'confidentiality' in penalties_content.lower():
            # Split the combined content
            lines = penalties_content.split('\n')
            new_penalties = []
            current_section = 'penalties'
            
            for line in lines:
                line_lower = line.strip().lower()
                if 'confidentiality' in line_lower:
                    # Start new section
                    if new_penalties:
                        blocks['penalties'] = '\n'.join(new_penalties).strip()
                    current_section = 'confidentiality'
                    new_section = [line]
                elif 'force majeure' in line_lower:
                    if current_section == 'confidentiality' and new_section:
                        blocks['confidentiality'] = '\n'.join(new_section).strip()
                    current_section = 'force_majeure'
                    new_section = [line]
                elif 'termination' in line_lower:
                    if current_section == 'force_majeure' and new_section:
                        blocks['force_majeure'] = '\n'.join(new_section).strip()
                    current_section = 'termination'
                    new_section = [line]
                elif 'dispute resolution' in line_lower:
                    if current_section == 'termination' and new_section:
                        blocks['termination'] = '\n'.join(new_section).strip()
                    current_section = 'dispute_resolution'
                    new_section = [line]
                elif 'digital signatures' in line_lower:
                    if current_section == 'dispute_resolution' and new_section:
                        blocks['dispute_resolution'] = '\n'.join(new_section).strip()
                    current_section = 'digital_signatures'
                    new_section = [line]
                else:
                    if current_section == 'penalties':
                        new_penalties.append(line)
                    else:
                        new_section.append(line)
            
            # Save the final section
            if current_section == 'confidentiality' and new_section:
                blocks['confidentiality'] = '\n'.join(new_section).strip()
            elif current_section == 'force_majeure' and new_section:
                blocks['force_majeure'] = '\n'.join(new_section).strip()
            elif current_section == 'termination' and new_section:
                blocks['termination'] = '\n'.join(new_section).strip()
            elif current_section == 'dispute_resolution' and new_section:
                blocks['dispute_resolution'] = '\n'.join(new_section).strip()
            elif current_section == 'digital_signatures' and new_section:
                blocks['digital_signatures'] = '\n'.join(new_section).strip()
        
        # Ensure all blocks have content (fallback to default if empty)
        for block_name in blocks:
            if not blocks[block_name]:
                blocks[block_name] = self._get_default_block_content(block_name)
        
        return blocks

    def _get_default_block_content(self, block_name: str) -> str:
        """Provide default content for empty blocks"""
        defaults = {
            'title': 'Vendor Supply Agreement',
            'contract_id': f'Contract ID: {self.contract_id}\nEffective Date: {self.today}\nEnd Date: {self.one_year_later}',
            'parties_intro': 'This Agreement is made between the parties identified below.',
            'buyer': 'Buyer:\nEnterprise Name: [BUYER NAME]\nAddress: [BUYER ADDRESS]',
            'supplier': 'Supplier:\nVendor Name: [SUPPLIER NAME]\nAddress: [SUPPLIER ADDRESS]',
            'scope': 'SCOPE OF AGREEMENT\n• [Scope details to be specified]',
            'commercial': 'COMMERCIAL TERMS\n• [Commercial terms to be specified]',
            'delivery': 'DELIVERY TERMS\n• [Delivery terms to be specified]',
            'quality': 'QUALITY ASSURANCE\n• [Quality standards to be specified]',
            'penalties': 'PENALTIES AND LIABILITIES\n• [Penalties and liabilities to be specified]',
            'confidentiality': 'CONFIDENTIALITY\n• [Confidentiality terms to be specified]',
            'force_majeure': 'FORCE MAJEURE\n• [Force majeure terms to be specified]',
            'termination': 'TERMINATION\n• [Termination terms to be specified]',
            'dispute_resolution': 'DISPUTE RESOLUTION\n• [Dispute resolution terms to be specified]',
            'digital_signatures': 'DIGITAL SIGNATURES\n• [Digital signature terms to be specified]'
        }
        return defaults.get(block_name, '')

    # Individual getter methods for each block
    def get_title_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('title', '')

    def get_contract_id(self, agreement: Dict[str, str]) -> str:
        return agreement.get('contract_id', '')
    
    def get_parties_intro(self, agreement: Dict[str, str]) -> str:
        return agreement.get('parties_intro', '')

    def get_buyer_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('buyer', '')

    def get_supplier_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('supplier', '')

    def get_scope_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('scope', '')

    def get_commercial_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('commercial', '')

    def get_delivery_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('delivery', '')

    def get_quality_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('quality', '')

    def get_penalties_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('penalties', '')

    def get_confidentiality_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('confidentiality', '')
    
    def get_force_majeure_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('force_majeure', '')

    def get_termination_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('termination', '')

    def get_dispute_resolution_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('dispute_resolution', '')

    def get_digital_signatures_block(self, agreement: Dict[str, str]) -> str:
        return agreement.get('digital_signatures', '')
    
    
    