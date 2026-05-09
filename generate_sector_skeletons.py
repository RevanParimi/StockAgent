"""
generate_sector_skeletons.py
============================
Generates agent skeleton files for 19 sectors (all except automobile & renewable).
Run from project root: python generate_sector_skeletons.py
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Sector definitions
# ---------------------------------------------------------------------------
SECTORS = [
    dict(folder="defence",     prefix="Def",      display="Defence & Aerospace",        const="defence",
         w=dict(fundamentals=0.22,management=0.12,business=0.12,macro=0.15,risk=0.10,valuation=0.15,technical=0.09,earnings=0.05),
         pillars=dict(
             business=dict(sys="You are a defence sector analyst specialising in Indian defence & aerospace companies. Expert in order books, DRDO programmes, offset obligations, export potential, and indigenisation ratios.",
                           dims=["Order Book & Revenue Visibility","Indigenisation Ratio & DRDO Tie-ups","Export Potential & Offset Obligations","Product Mix & Technology Edge","New Programme Wins"],
                           subs=["order_book","indigenisation","exports","product_mix","programme_wins"],
                           qs=["{ticker} order book defence contracts {year}","{company_name} indigenisation DRDO programme {year}","{ticker} defence export offset {year}","{ticker} new order wins {quarter} {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian defence companies. Expert in EBITDA margins, working capital cycles (long defence procurement), RoCE, and debt management.",
                               dims=["Revenue Growth & Order Conversion","EBITDA Margin Trend","RoCE & Capital Efficiency","Working Capital & Cash Conversion","Net Debt / EBITDA"],
                               subs=["revenue_growth","ebitda_margin","roce","working_capital","net_debt_ebitda"],
                               qs=["{ticker} revenue EBITDA margin {quarter} {year}","{company_name} RoCE capital efficiency {year}","{ticker} working capital cash flow defence {year}","{ticker} net debt balance sheet {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian defence stocks. Expert in EV/EBITDA, P/E vs order-book multiples, and SOTP for diversified defence players.",
                            dims=["P/E vs Sector Peers","EV/EBITDA","EV/Order Book","Price/Book","SOTP Valuation"],
                            subs=["pe_ratio","ev_ebitda","ev_order_book","price_book","sotp"],
                            qs=["{ticker} P/E EV/EBITDA valuation defence {year}","{company_name} valuation peer comparison {year}","{ticker} order book multiple EV {year}"]),
             technical=dict(sys="You are a technical analyst specialising in Indian mid/large-cap defence stocks.",
                            dims=["Trend (50/200 DMA)","RSI Momentum","MACD Signal","Volume Confirmation","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} stock price technical analysis {year}","{ticker} NSE 52-week high low support {year}"]),
             macro=dict(sys="You are a macro analyst for Indian defence sector. Expert in defence budget, FDI policy, geopolitical triggers, and SIPRI data.",
                        dims=["Defence Budget Allocation","FDI & Private Sector Policy","Geopolitical Risk Premium","HAL/BEL/DRDO Order Pipeline","Offset & Make-in-India Policy"],
                        subs=["defence_budget","fdi_policy","geopolitical","order_pipeline","make_in_india"],
                        qs=["India defence budget allocation {year}","Make in India defence policy {year}","India geopolitical risk defence spending {year}","{ticker} government order pipeline {year}"]),
             risk=dict(sys="You are a risk analyst for Indian defence companies. Expert in programme delays, payment cycles, competition risks, and regulatory risks.",
                       dims=["Programme Delay Risk","Payment & Receivable Risk","Competition from Imports","Regulatory & Export Control","Concentration Risk"],
                       subs=["programme_delay","payment_risk","import_competition","regulatory","concentration"],
                       qs=["{ticker} programme delay risk {year}","{company_name} receivables government payment {year}","{ticker} competition imports defence {year}"]),
             management=dict(sys="You are a governance analyst for Indian defence PSUs and private players. Expert in promoter quality, succession, and RPT.",
                             dims=["Promoter Integrity & Track Record","Capital Allocation Discipline","RPT & Subsidiary Risk","Management Guidance Accuracy","ESG & Governance Score"],
                             subs=["promoter_integrity","capital_allocation","rpt_risk","guidance_accuracy","esg"],
                             qs=["{ticker} management promoter governance {year}","{company_name} RPT related party {year}","{ticker} capital allocation dividend buyback {year}"]),
             earnings=dict(sys="You are an earnings quality analyst for Indian defence companies.",
                           dims=["Revenue Recognition Policy","Order-to-Revenue Conversion","Margin Trajectory","Exceptional Items","Guidance vs Actual"],
                           subs=["revenue_recognition","order_conversion","margin_trajectory","exceptional_items","guidance_accuracy"],
                           qs=["{ticker} quarterly results earnings {quarter} {year}","{company_name} revenue recognition policy defence {year}","{ticker} margin guidance actual {year}"]),
         )),
    dict(folder="tech",        prefix="IT",       display="Information Technology",      const="tech",
         w=dict(fundamentals=0.16,management=0.11,business=0.20,macro=0.08,risk=0.08,valuation=0.20,technical=0.10,earnings=0.07),
         pillars=dict(
             business=dict(sys="You are an IT sector analyst for Indian technology companies. Expert in deal TCV, revenue mix (services vs products), digital transformation, AI/cloud adoption, and client concentration.",
                           dims=["Deal TCV & Win Rate","Revenue Mix (Digital vs Legacy)","Client Concentration & Mining","Vertical Mix & Growth","AI/GenAI Positioning"],
                           subs=["deal_tcv","revenue_mix","client_concentration","vertical_mix","ai_positioning"],
                           qs=["{ticker} deal wins TCV {quarter} {year}","{company_name} digital revenue cloud {year}","{ticker} client concentration top accounts {year}","{ticker} AI GenAI strategy {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian IT services companies. Expert in EBIT margins, revenue growth, attrition impact, USD/INR hedging, and free cash flow conversion.",
                               dims=["Revenue Growth (CC & INR)","EBIT Margin Trend","Free Cash Flow Conversion","Attrition & Headcount","USD Hedge Book"],
                               subs=["revenue_growth","ebit_margin","fcf_conversion","attrition","usd_hedge"],
                               qs=["{ticker} revenue growth EBIT margin {quarter} {year}","{company_name} attrition headcount {year}","{ticker} free cash flow USD hedge {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian IT stocks. Expert in P/E, EV/EBITDA, PEG ratio, and premium/discount to TCS.",
                            dims=["P/E vs Sector Peers","EV/EBITDA","PEG Ratio","Price/FCF","Premium to TCS"],
                            subs=["pe_ratio","ev_ebitda","peg_ratio","price_fcf","tcs_premium"],
                            qs=["{ticker} P/E EV/EBITDA IT sector valuation {year}","{company_name} vs TCS Infosys multiple {year}"]),
             technical=dict(sys="You are a technical analyst for Indian IT large/mid-cap stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} stock technical analysis {year}","{ticker} NSE price 52-week {year}"]),
             macro=dict(sys="You are a macro analyst for Indian IT sector. Expert in US tech spending, Fed rates, USDINR, H1B visa policy, and GenAI disruption.",
                        dims=["US IT Spending Outlook","Fed Rate & USD/INR","H1B Visa Policy","GenAI Disruption Risk","European Demand"],
                        subs=["us_spending","usd_inr","h1b","genai_disruption","europe_demand"],
                        qs=["US enterprise IT spending {year}","Fed rate USD INR impact Indian IT {year}","H1B visa policy India IT {year}","GenAI disruption IT services {year}"]),
             risk=dict(sys="You are a risk analyst for Indian IT companies. Expert in pricing pressure, automation risk, deal ramp-down, and client industry exposure.",
                       dims=["Pricing Pressure & Commoditisation","Automation & AI Displacement","Large Deal Ramp Risk","BFSI/Retail Client Exposure","Regulatory & Data Privacy"],
                       subs=["pricing_pressure","automation_risk","deal_ramp","sector_exposure","regulatory"],
                       qs=["{ticker} pricing pressure deal ramp {year}","{company_name} BFSI retail exposure risk {year}"]),
             management=dict(sys="You are a governance analyst for Indian IT companies.",
                             dims=["CEO Track Record & Vision","Capital Allocation (Buyback/Dividend)","RPT & Subsidiary Risk","Bench Strength","ESG"],
                             subs=["ceo_track_record","capital_allocation","rpt","bench_strength","esg"],
                             qs=["{ticker} management CEO capital allocation {year}","{company_name} buyback dividend {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian IT companies.",
                           dims=["Revenue Guidance Adherence","Margin Guidance vs Actual","Deal Conversion to Revenue","Forex Impact","One-time Items"],
                           subs=["revenue_guidance","margin_guidance","deal_conversion","forex_impact","one_time"],
                           qs=["{ticker} earnings guidance actual {quarter} {year}","{company_name} margin forex impact {year}"]),
         )),
    dict(folder="banking",     prefix="Bank",     display="Banking & NBFC",              const="banking",
         w=dict(fundamentals=0.18,management=0.13,business=0.08,macro=0.15,risk=0.22,valuation=0.07,technical=0.09,earnings=0.08),
         pillars=dict(
             business=dict(sys="You are a banking sector analyst for Indian banks and NBFCs. Expert in loan mix, CASA ratio, fee income, and retail vs corporate franchise.",
                           dims=["Loan Book Growth & Mix","CASA Ratio & Deposit Franchise","Fee Income & Cross-sell","Retail vs Corporate Mix","Market Share"],
                           subs=["loan_growth","casa_ratio","fee_income","retail_corporate_mix","market_share"],
                           qs=["{ticker} loan growth CASA ratio {quarter} {year}","{company_name} retail corporate loan mix {year}","{ticker} fee income {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian banks. Expert in NIM, RoA, RoE, CET1, cost-to-income ratio.",
                               dims=["NIM (Net Interest Margin)","RoA & RoE","CET1 Capital Adequacy","Cost-to-Income Ratio","Provision Coverage Ratio"],
                               subs=["nim","roa_roe","cet1","cost_income","pcr"],
                               qs=["{ticker} NIM RoA RoE {quarter} {year}","{company_name} CET1 capital adequacy {year}","{ticker} cost income ratio provisions {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian bank stocks. Expert in P/BV, P/ABV, and RoE-based fair value.",
                            dims=["P/BV vs Peers","P/ABV","RoE-based Target","Franchise Premium","P/E"],
                            subs=["pbv","pabv","roe_based","franchise_premium","pe"],
                            qs=["{ticker} P/BV P/ABV banking valuation {year}","{company_name} vs HDFC ICICI multiple {year}"]),
             technical=dict(sys="You are a technical analyst for Indian banking stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} stock price technical {year}","{ticker} Nifty Bank relative performance {year}"]),
             macro=dict(sys="You are a macro analyst for Indian banking sector. Expert in RBI policy, credit growth, liquidity, and MSME/infra credit cycles.",
                        dims=["RBI Repo Rate & Liquidity","System Credit Growth","Deposit Competition","MSME & Agri Policy","Currency & Inflation"],
                        subs=["rbi_rate","credit_growth","deposit_competition","msme_policy","currency"],
                        qs=["RBI repo rate banking credit growth India {year}","India banking system liquidity deposit {year}","RBI MSME credit policy {year}"]),
             risk=dict(sys="You are a credit risk analyst for Indian banks. Expert in GNPA, NNPA, SMA-2, slippage ratio, and stress-testing.",
                       dims=["GNPA & NNPA Trend","Slippage Ratio","Restructured Book & SMA-2","Sector Concentration (Real Estate, MSME)","Provisioning Adequacy"],
                       subs=["gnpa_nnpa","slippage","restructured_book","sector_concentration","provisioning"],
                       qs=["{ticker} GNPA NNPA slippage {quarter} {year}","{company_name} restructured book SMA {year}","{ticker} sector concentration real estate {year}"]),
             management=dict(sys="You are a governance analyst for Indian banks.",
                             dims=["MD/CEO Track Record","RBI Regulatory Actions","Capital Allocation","Succession Planning","ESG & Financial Inclusion"],
                             subs=["ceo_track_record","rbi_actions","capital_allocation","succession","esg"],
                             qs=["{ticker} CEO management RBI action {year}","{company_name} capital allocation dividend {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian banks.",
                           dims=["NII Growth vs Guidance","Pre-Provision Operating Profit","Credit Cost Trend","One-time Provisions","Fee Income Growth"],
                           subs=["nii_growth","ppop","credit_cost","one_time","fee_growth"],
                           qs=["{ticker} NII PPOP credit cost {quarter} {year}","{company_name} earnings quality provisions {year}"]),
         )),
    dict(folder="pharma",      prefix="Pharma",   display="Pharmaceuticals",             const="pharma",
         w=dict(fundamentals=0.16,management=0.11,business=0.18,macro=0.08,risk=0.16,valuation=0.15,technical=0.10,earnings=0.06),
         pillars=dict(
             business=dict(sys="You are a pharma sector analyst for Indian pharmaceutical companies. Expert in US FDA pipeline, domestic formulations, API backward integration, and CDMO business.",
                           dims=["US FDA Pipeline & ANDA Filings","Domestic Formulations Market Share","API/CDMO Business","Specialty/Branded Mix","New Therapy Area Entry"],
                           subs=["us_pipeline","domestic_share","api_cdmo","specialty_mix","new_therapy"],
                           qs=["{ticker} US FDA ANDA pipeline {year}","{company_name} domestic formulations market share {year}","{ticker} API CDMO business {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian pharma companies. Expert in EBITDA margins, R&D spend, working capital, and free cash flow.",
                               dims=["Revenue Growth & Mix","EBITDA Margin","R&D Spend (% Revenue)","Working Capital","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","rd_spend","working_capital","fcf"],
                               qs=["{ticker} EBITDA margin R&D spend {quarter} {year}","{company_name} revenue growth working capital {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian pharma stocks.",
                            dims=["P/E vs Pharma Peers","EV/EBITDA","EV/R&D Adjusted","Price/FCF","Pipeline NPV"],
                            subs=["pe","ev_ebitda","ev_rd","price_fcf","pipeline_npv"],
                            qs=["{ticker} P/E EV/EBITDA pharma valuation {year}","{company_name} pipeline NPV valuation {year}"]),
             technical=dict(sys="You are a technical analyst for Indian pharma stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} stock price technical analysis {year}"]),
             macro=dict(sys="You are a macro analyst for Indian pharma. Expert in US drug pricing policy, FDA import alerts, generic competition, and Indian domestic pricing.",
                        dims=["US Drug Pricing Policy","FDA Import Alerts","Generic Price Erosion","NPPA Pricing Regulation","China API Competition"],
                        subs=["us_pricing","fda_alerts","generic_erosion","nppa","china_api"],
                        qs=["US drug pricing policy FDA {year}","India NPPA pharma pricing regulation {year}","China API competition India pharma {year}"]),
             risk=dict(sys="You are a risk analyst for Indian pharma companies. Expert in FDA 483s, USFDA import alerts, patent cliffs, and pricing pressure.",
                       dims=["USFDA 483 & Warning Letter Risk","Patent Cliff Exposure","Pricing Pressure in US Generics","Regulatory Compliance Cost","Single-Product Concentration"],
                       subs=["fda_risk","patent_cliff","pricing_pressure","compliance_cost","concentration"],
                       qs=["{ticker} USFDA 483 warning letter {year}","{company_name} patent cliff risk {year}","{ticker} US generics pricing {year}"]),
             management=dict(sys="You are a governance analyst for Indian pharma companies.",
                             dims=["Promoter Quality","R&D Strategy Execution","Capital Allocation","Regulatory Track Record","ESG"],
                             subs=["promoter_quality","rd_execution","capital_allocation","regulatory_track","esg"],
                             qs=["{ticker} management R&D strategy {year}","{company_name} capital allocation promoter {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian pharma.",
                           dims=["US Revenue Guidance vs Actual","Domestic Growth","R&D Capitalisation Policy","One-time Charges","EBITDA Guidance"],
                           subs=["us_guidance","domestic_growth","rd_policy","one_time","ebitda_guidance"],
                           qs=["{ticker} earnings guidance US domestic {quarter} {year}","{company_name} EBITDA one-time items {year}"]),
         )),
    dict(folder="fmcg",        prefix="FMCG",     display="FMCG & Consumer Staples",     const="fmcg",
         w=dict(fundamentals=0.16,management=0.12,business=0.19,macro=0.12,risk=0.07,valuation=0.18,technical=0.09,earnings=0.07),
         pillars=dict(
             business=dict(sys="You are an FMCG analyst for Indian consumer staples companies. Expert in volume growth, distribution reach, market share, and premiumisation.",
                           dims=["Volume Growth & Market Share","Distribution & Rural Reach","Premiumisation Trend","New Category Entry","Brand Strength"],
                           subs=["volume_growth","distribution","premiumisation","new_category","brand_strength"],
                           qs=["{ticker} volume growth market share {quarter} {year}","{company_name} distribution rural reach {year}","{ticker} premiumisation new products {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian FMCG companies. Expert in gross margins, A&P spend, EBITDA margins, and ROCE.",
                               dims=["Gross Margin Trend","A&P Spend (% Revenue)","EBITDA Margin","ROCE","Working Capital"],
                               subs=["gross_margin","ap_spend","ebitda_margin","roce","working_capital"],
                               qs=["{ticker} gross margin EBITDA A&P spend {quarter} {year}","{company_name} ROCE working capital {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian FMCG stocks. Expert in premium P/E multiples and DCF for consumer franchises.",
                            dims=["P/E vs FMCG Peers","EV/EBITDA","Price/FCF","Dividend Yield","DCF Intrinsic Value"],
                            subs=["pe","ev_ebitda","price_fcf","div_yield","dcf"],
                            qs=["{ticker} P/E EV/EBITDA FMCG valuation {year}","{company_name} vs HUL ITC multiple {year}"]),
             technical=dict(sys="You are a technical analyst for Indian FMCG stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} FMCG stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian FMCG sector. Expert in rural demand, commodity input costs, inflation, and GST.",
                        dims=["Rural Demand & Monsoon","Commodity Input Costs (Palm Oil, Wheat)","CPI Inflation & Pricing Power","GST & Regulatory","Urban Consumption"],
                        subs=["rural_demand","commodity_costs","inflation_pricing","gst","urban_consumption"],
                        qs=["India rural demand FMCG consumption {year}","Palm oil wheat commodity prices India {year}","India CPI inflation FMCG pricing {year}"]),
             risk=dict(sys="You are a risk analyst for Indian FMCG companies.",
                       dims=["Raw Material Cost Volatility","D2C & Private Label Competition","Rural Slowdown Risk","Regulatory (FSSAI, GST)","Concentration in Key SKUs"],
                       subs=["rm_volatility","competition","rural_risk","regulatory","sku_concentration"],
                       qs=["{ticker} raw material risk commodity {year}","{company_name} competition D2C private label {year}"]),
             management=dict(sys="You are a governance analyst for Indian FMCG companies.",
                             dims=["Promoter/MNC Parent Quality","Capital Allocation","RPT with Parent","A&P Efficiency","ESG"],
                             subs=["promoter_quality","capital_allocation","rpt","ap_efficiency","esg"],
                             qs=["{ticker} management promoter capital allocation {year}","{company_name} RPT parent {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian FMCG.",
                           dims=["Volume vs Price Growth","Gross Margin Trajectory","A&P Cuts vs Brand Health","Guidance vs Actual","Premiumisation Revenue Share"],
                           subs=["volume_price","gross_margin","ap_cuts","guidance","premium_share"],
                           qs=["{ticker} volume price growth earnings {quarter} {year}","{company_name} margin guidance {year}"]),
         )),
    dict(folder="infra",       prefix="Infra",    display="Infrastructure & Construction",const="infra",
         w=dict(fundamentals=0.18,management=0.12,business=0.16,macro=0.16,risk=0.12,valuation=0.14,technical=0.09,earnings=0.03),
         pillars=dict(
             business=dict(sys="You are an infrastructure analyst for Indian construction and infra companies. Expert in order books, L1 bid pipeline, HAM/EPC mix, and government capex.",
                           dims=["Order Book & L1 Pipeline","EPC vs HAM Mix","Sector Diversification","Geographic Mix","Execution Track Record"],
                           subs=["order_book","epc_ham_mix","sector_diversification","geo_mix","execution"],
                           qs=["{ticker} order book L1 pipeline {year}","{company_name} EPC HAM roads infra {year}","{ticker} execution capex {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian infra/construction companies. Expert in EBITDA margins, working capital, D/E ratio, and cash conversion.",
                               dims=["Revenue Growth & Order Conversion","EBITDA Margin","Debt/Equity & Interest Cover","Working Capital Cycle","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","debt_equity","working_capital","fcf"],
                               qs=["{ticker} EBITDA margin debt equity {quarter} {year}","{company_name} working capital cash flow {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian infra stocks. Expert in EV/Order Book and P/E for construction.",
                            dims=["EV/Order Book","P/E vs Peers","EV/EBITDA","Price/Book","SOTP"],
                            subs=["ev_order_book","pe","ev_ebitda","price_book","sotp"],
                            qs=["{ticker} EV order book valuation infra {year}","{company_name} P/E peer comparison {year}"]),
             technical=dict(sys="You are a technical analyst for Indian infra stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} stock technical analysis {year}"]),
             macro=dict(sys="You are a macro analyst for Indian infrastructure sector. Expert in government capex budgets, NIP, NHAI pipeline, and RBI rate impact on project viability.",
                        dims=["Government Capex Budget","NHAI/Railways/Airport Pipeline","RBI Rate & Project IRR","State Capex Spend","PLI & Industrial Capex"],
                        subs=["govt_capex","nhai_pipeline","rbi_rate","state_capex","pli"],
                        qs=["India government capex budget infrastructure {year}","NHAI roads railways airport pipeline {year}","India infrastructure NIP {year}"]),
             risk=dict(sys="You are a risk analyst for Indian infra companies.",
                       dims=["Working Capital Stress","Land Acquisition & Litigation","Project Execution Delays","Debt Refinancing Risk","Government Payment Risk"],
                       subs=["working_capital","land_litigation","execution_delay","refinancing","payment_risk"],
                       qs=["{ticker} working capital land litigation risk {year}","{company_name} project delay execution {year}"]),
             management=dict(sys="You are a governance analyst for Indian infra companies.",
                             dims=["Promoter Quality & Track Record","Related Party Transactions","Capital Allocation","Concession Portfolio","ESG"],
                             subs=["promoter_quality","rpt","capital_allocation","concession","esg"],
                             qs=["{ticker} management promoter {year}","{company_name} RPT capital allocation {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian infra/construction companies.",
                           dims=["Revenue Recognition (POC vs Completion)","Order Book-to-Revenue Conversion","Margin Trajectory","Exceptional Items","Guidance vs Actual"],
                           subs=["revenue_recognition","ob_conversion","margin","exceptional","guidance"],
                           qs=["{ticker} earnings revenue recognition {quarter} {year}","{company_name} margin guidance {year}"]),
         )),
    dict(folder="metals",      prefix="Metal",    display="Metals & Mining",             const="metals",
         w=dict(fundamentals=0.16,management=0.09,business=0.10,macro=0.18,risk=0.11,valuation=0.15,technical=0.16,earnings=0.05),
         pillars=dict(
             business=dict(sys="You are a metals & mining analyst for Indian companies. Expert in mining integration, product mix, capacity utilisation, and exports.",
                           dims=["Captive Mining Integration","Capacity & Utilisation Rate","Product Mix (Flat/Long/Special)","Export Revenue Share","Downstream Value Addition"],
                           subs=["mining_integration","capacity_utilisation","product_mix","export_share","downstream"],
                           qs=["{ticker} mining integration capacity {year}","{company_name} product mix flat long steel {year}","{ticker} export revenue {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian metals companies. Expert in EBITDA/tonne, net debt, coking coal costs, and FCF.",
                               dims=["EBITDA/Tonne","Revenue per Tonne","Net Debt & Leverage","Coking Coal / Iron Ore Cost","FCF Yield"],
                               subs=["ebitda_tonne","revenue_tonne","net_debt","input_cost","fcf_yield"],
                               qs=["{ticker} EBITDA per tonne net debt {quarter} {year}","{company_name} coking coal cost iron ore {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian metals stocks.",
                            dims=["EV/EBITDA vs Cycle","P/E Normalised","EV/Tonne","Price/Book","Replacement Cost"],
                            subs=["ev_ebitda","pe_normalised","ev_tonne","price_book","replacement_cost"],
                            qs=["{ticker} EV/EBITDA metals cycle valuation {year}","{company_name} EV per tonne {year}"]),
             technical=dict(sys="You are a technical analyst for Indian metals stocks. Key indicator: LME price correlation.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","LME Price Correlation"],
                            subs=["trend","rsi","macd","volume","lme_correlation"],
                            qs=["{ticker} stock technical LME correlation {year}"]),
             macro=dict(sys="You are a macro analyst for Indian metals. Expert in LME prices, China demand, USD strength, and infrastructure capex.",
                        dims=["LME Steel/Aluminium/Copper Prices","China Demand & PMI","USD Index","India Infra Capex Demand","Coking Coal & Iron Ore Prices"],
                        subs=["lme_prices","china_demand","usd_index","india_capex","input_prices"],
                        qs=["LME steel aluminium copper prices China demand {year}","China steel demand PMI {year}","India infrastructure demand steel {year}"]),
             risk=dict(sys="You are a risk analyst for Indian metals companies.",
                       dims=["Commodity Price Cycle Risk","China Dumping & Anti-dumping","Input Cost Volatility","Regulatory & Mining Lease Risk","Debt & Refinancing"],
                       subs=["price_cycle","china_dumping","input_volatility","regulatory","debt_risk"],
                       qs=["{ticker} China dumping anti-dumping metals {year}","{company_name} mining lease regulatory risk {year}"]),
             management=dict(sys="You are a governance analyst for Indian metals companies.",
                             dims=["Promoter Quality","Capex Discipline","RPT & Group Risk","ESG & Environment Compliance","Capital Allocation"],
                             subs=["promoter_quality","capex_discipline","rpt","esg","capital_allocation"],
                             qs=["{ticker} management capex ESG {year}","{company_name} RPT group risk {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian metals.",
                           dims=["Volume Growth","Realization Trend","EBITDA/Tonne vs LME","Input Cost Pass-through","One-time Items"],
                           subs=["volume_growth","realization","ebitda_vs_lme","pass_through","one_time"],
                           qs=["{ticker} volume realization EBITDA {quarter} {year}","{company_name} earnings LME {year}"]),
         )),
    dict(folder="oilgas",      prefix="OilGas",   display="Oil & Gas",                   const="oilgas",
         w=dict(fundamentals=0.14,management=0.10,business=0.10,macro=0.22,risk=0.12,valuation=0.14,technical=0.10,earnings=0.08),
         pillars=dict(
             business=dict(sys="You are an oil & gas analyst for Indian E&P and downstream companies. Expert in reserve life, refining margins, petchem, and gas transmission.",
                           dims=["Reserve Life Index (RLI)","Refining Complexity & GRM","Petchem Integration","Gas Transmission & CGD","Upstream Production Trend"],
                           subs=["rli","grm","petchem","gas_cgd","upstream_production"],
                           qs=["{ticker} reserve life refining margin GRM {year}","{company_name} petchem gas CGD business {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian oil & gas companies.",
                               dims=["Revenue & EBITDA Growth","GRM / EBITDA/boe","Net Debt & Leverage","Capex Cycle","FCF Generation"],
                               subs=["revenue_ebitda","grm_ebitda","net_debt","capex","fcf"],
                               qs=["{ticker} EBITDA GRM net debt {quarter} {year}","{company_name} capex FCF oil gas {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian oil & gas stocks.",
                            dims=["EV/EBITDA vs Brent Cycle","P/E","EV/boe (Reserves)","Price/Book","Dividend Yield"],
                            subs=["ev_ebitda","pe","ev_boe","price_book","div_yield"],
                            qs=["{ticker} EV/EBITDA oil gas valuation Brent {year}","{company_name} P/E reserve valuation {year}"]),
             technical=dict(sys="You are a technical analyst for Indian oil & gas stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Brent Oil Correlation"],
                            subs=["trend","rsi","macd","volume","brent_correlation"],
                            qs=["{ticker} technical stock Brent oil correlation {year}"]),
             macro=dict(sys="You are a macro analyst for Indian oil & gas. Expert in Brent crude, OPEC+ decisions, INR/USD, domestic fuel pricing, and gas APM policy.",
                        dims=["Brent Crude Price Outlook","OPEC+ Production Policy","USD/INR Impact","India Fuel Subsidy Policy","APM Gas Price"],
                        subs=["brent_crude","opec","usd_inr","subsidy_policy","apm_gas"],
                        qs=["Brent crude OPEC production {year}","India fuel subsidy pricing policy {year}","India APM gas price {year}","USD INR oil import {year}"]),
             risk=dict(sys="You are a risk analyst for Indian oil & gas companies.",
                       dims=["Crude Price Volatility","Subsidy Burden","Regulatory & Environmental","Exploration Dry-hole Risk","Geopolitical Supply Risk"],
                       subs=["crude_volatility","subsidy_burden","regulatory","exploration_risk","geopolitical"],
                       qs=["{ticker} subsidy burden regulatory risk {year}","{company_name} exploration dry hole risk {year}"]),
             management=dict(sys="You are a governance analyst for Indian oil & gas companies.",
                             dims=["PSU vs Private Management","Capital Allocation & Capex","RPT & Subsidiary","ESG & Carbon Goals","Succession"],
                             subs=["psu_private","capital_allocation","rpt","esg_carbon","succession"],
                             qs=["{ticker} management capital allocation ESG {year}","{company_name} RPT subsidiary {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian oil & gas.",
                           dims=["GRM vs Benchmark","Production Volume vs Guidance","Inventory Gains/Losses","Under-recovery Impact","Forex Impact"],
                           subs=["grm_vs_benchmark","production_volume","inventory","under_recovery","forex"],
                           qs=["{ticker} GRM earnings production {quarter} {year}","{company_name} under-recovery inventory gains {year}"]),
         )),
    dict(folder="realestate",  prefix="RealEst",  display="Real Estate & REITs",         const="realestate",
         w=dict(fundamentals=0.11,management=0.12,business=0.14,macro=0.18,risk=0.11,valuation=0.18,technical=0.09,earnings=0.07),
         pillars=dict(
             business=dict(sys="You are a real estate analyst for Indian developers and REITs. Expert in presales, GDV, launch pipeline, and REIT distributions.",
                           dims=["Presales & Collections","Launch Pipeline & GDV","Geographical Diversification","Affordable vs Luxury Mix","REIT Distribution Yield"],
                           subs=["presales","launch_pipeline","geo_diversification","product_mix","reit_yield"],
                           qs=["{ticker} presales collections launch pipeline {year}","{company_name} GDV residential commercial {year}","{ticker} REIT distribution {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian real estate companies.",
                               dims=["Revenue Recognition (Completion Method)","EBITDA Margin","Net Debt & Leverage","Operating Cash Flow","Land Bank Value"],
                               subs=["revenue_recognition","ebitda_margin","net_debt","operating_cf","land_bank"],
                               qs=["{ticker} revenue EBITDA net debt real estate {year}","{company_name} land bank cash flow {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian real estate stocks.",
                            dims=["NAV Premium/Discount","EV/EBITDA","Price/Presales","P/Book","REIT Cap Rate"],
                            subs=["nav_discount","ev_ebitda","price_presales","price_book","cap_rate"],
                            qs=["{ticker} NAV valuation real estate {year}","{company_name} EV/EBITDA P/book {year}"]),
             technical=dict(sys="You are a technical analyst for Indian real estate stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} real estate stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian real estate. Expert in RBI repo rate, home loan rates, housing affordability, and government schemes.",
                        dims=["RBI Repo Rate & Home Loan Rates","Housing Affordability Index","PMAY & Government Schemes","Commercial Real Estate Demand","NRI Demand"],
                        subs=["rbi_home_loan","affordability","pmay","commercial_demand","nri"],
                        qs=["India home loan rates RBI real estate {year}","India housing affordability PMAY {year}","Commercial real estate demand {year}"]),
             risk=dict(sys="You are a risk analyst for Indian real estate companies.",
                       dims=["Project Delivery Delays","RERA Compliance","Working Capital & Debt","Unsold Inventory","Regulatory Changes (RERA, GST)"],
                       subs=["delivery_delay","rera_compliance","debt_risk","unsold_inventory","regulatory"],
                       qs=["{ticker} RERA project delay delivery risk {year}","{company_name} unsold inventory debt {year}"]),
             management=dict(sys="You are a governance analyst for Indian real estate developers.",
                             dims=["Promoter Track Record & Delivery","Capital Allocation","RPT & Land Deals","Corporate Governance","ESG"],
                             subs=["promoter_delivery","capital_allocation","rpt","governance","esg"],
                             qs=["{ticker} promoter track record delivery {year}","{company_name} RPT land deals {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian real estate.",
                           dims=["Presales vs Revenue Recognition Lag","Collections Efficiency","Margin on Completed Projects","New Launch Performance","Guidance vs Actual"],
                           subs=["presales_recognition","collections","project_margin","launch_performance","guidance"],
                           qs=["{ticker} presales collections earnings {quarter} {year}","{company_name} margin guidance real estate {year}"]),
         )),
    dict(folder="chemicals",   prefix="Chem",     display="Specialty Chemicals",         const="chemicals",
         w=dict(fundamentals=0.20,management=0.12,business=0.20,macro=0.12,risk=0.08,valuation=0.15,technical=0.07,earnings=0.06),
         pillars=dict(
             business=dict(sys="You are a specialty chemicals analyst for Indian companies. Expert in import substitution, China+1 positioning, CRAMS/CDMO, and agrochemical AIs.",
                           dims=["China+1 Market Share Gain","CRAMS/CDMO Business","Import Substitution Pipeline","Customer Concentration","New Product Pipeline"],
                           subs=["china_plus_1","crams_cdmo","import_substitution","customer_concentration","new_products"],
                           qs=["{ticker} China+1 specialty chemicals CRAMS {year}","{company_name} import substitution pipeline {year}","{ticker} CDMO customer concentration {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian specialty chemical companies.",
                               dims=["Revenue Growth & Mix","EBITDA Margin","ROCE & Asset Turns","R&D Spend","Working Capital"],
                               subs=["revenue_growth","ebitda_margin","roce","rd_spend","working_capital"],
                               qs=["{ticker} EBITDA margin ROCE specialty chemicals {year}","{company_name} R&D working capital {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian specialty chemical stocks.",
                            dims=["P/E vs Peers","EV/EBITDA","EV/Sales","Price/Book","DCF"],
                            subs=["pe","ev_ebitda","ev_sales","price_book","dcf"],
                            qs=["{ticker} P/E EV/EBITDA chemicals valuation {year}","{company_name} vs SRF Navin Fluorine multiple {year}"]),
             technical=dict(sys="You are a technical analyst for Indian specialty chemical stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} chemicals stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian specialty chemicals. Expert in China environmental regulations, crude derivatives pricing, and export opportunities.",
                        dims=["China Environmental Crackdown Impact","Crude Oil & Derivatives Pricing","Export Demand (Europe/US)","India Chemical PLI","Currency Impact"],
                        subs=["china_regulation","crude_derivatives","export_demand","pli","currency"],
                        qs=["China chemical regulation environmental {year}","Specialty chemicals export India {year}","India chemical PLI {year}"]),
             risk=dict(sys="You are a risk analyst for Indian specialty chemical companies.",
                       dims=["Raw Material Cost Volatility","Customer Concentration Risk","China Competition Return","Regulatory (REACH, BIS)","Capex Execution"],
                       subs=["rm_volatility","customer_concentration","china_competition","regulatory","capex_execution"],
                       qs=["{ticker} raw material cost risk {year}","{company_name} China competition regulatory chemicals {year}"]),
             management=dict(sys="You are a governance analyst for Indian specialty chemical companies.",
                             dims=["Promoter Quality","R&D Strategy","Capital Allocation","RPT","ESG & Environment"],
                             subs=["promoter_quality","rd_strategy","capital_allocation","rpt","esg"],
                             qs=["{ticker} management promoter R&D {year}","{company_name} capital allocation chemicals {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian specialty chemicals.",
                           dims=["Volume vs Realization","EBITDA Margin Trend","Utilisation Rate","New Product Revenue","Guidance vs Actual"],
                           subs=["volume_realization","ebitda_margin","utilisation","new_product","guidance"],
                           qs=["{ticker} volume realization EBITDA {quarter} {year}","{company_name} utilisation guidance {year}"]),
         )),
    dict(folder="telecom",     prefix="Telecom",  display="Telecommunications",          const="telecom",
         w=dict(fundamentals=0.16,management=0.10,business=0.15,macro=0.19,risk=0.12,valuation=0.15,technical=0.07,earnings=0.06),
         pillars=dict(
             business=dict(sys="You are a telecom analyst for Indian operators. Expert in ARPU, subscriber mix, 5G rollout, enterprise business, and fixed broadband.",
                           dims=["ARPU Trend & Subscriber Mix","5G Rollout & Spectrum","Enterprise & B2B Revenue","Fixed Broadband (FTTH)","Market Share"],
                           subs=["arpu","5g_spectrum","enterprise_b2b","ftth","market_share"],
                           qs=["{ticker} ARPU subscriber 5G {quarter} {year}","{company_name} enterprise broadband FTTH {year}","{ticker} market share telecom India {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian telecom companies.",
                               dims=["Revenue & EBITDA Growth","EBITDA Margin","Net Debt & AGR Dues","Capex Intensity","FCF Generation"],
                               subs=["revenue_ebitda","ebitda_margin","net_debt_agr","capex","fcf"],
                               qs=["{ticker} EBITDA net debt AGR {quarter} {year}","{company_name} capex FCF telecom {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian telecom stocks.",
                            dims=["EV/EBITDA vs Peers","EV/Subscriber","P/E","Price/Book","DCF/SOTP"],
                            subs=["ev_ebitda","ev_subscriber","pe","price_book","dcf"],
                            qs=["{ticker} EV/EBITDA telecom valuation {year}","{company_name} EV per subscriber {year}"]),
             technical=dict(sys="You are a technical analyst for Indian telecom stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} telecom stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian telecom sector. Expert in spectrum auctions, TRAI regulations, government levies, and 5G policy.",
                        dims=["Spectrum Auction & 5G Policy","TRAI Tariff Regulation","AGR & Govt Dues","Tower Infrastructure Policy","Digital India Demand"],
                        subs=["spectrum_5g","trai_tariff","agr_dues","tower_policy","digital_india"],
                        qs=["India 5G spectrum auction TRAI telecom {year}","AGR dues Supreme Court telecom India {year}","India Digital India telecom policy {year}"]),
             risk=dict(sys="You are a risk analyst for Indian telecom companies.",
                       dims=["AGR & Regulatory Liability","High Debt & Refinancing","Competitive Pricing Risk (Jio)","Spectrum Renewal Cost","Capex Overrun"],
                       subs=["agr_liability","debt_refinancing","jio_competition","spectrum_renewal","capex_overrun"],
                       qs=["{ticker} AGR debt risk Jio competition {year}","{company_name} spectrum renewal capex {year}"]),
             management=dict(sys="You are a governance analyst for Indian telecom companies.",
                             dims=["Promoter Quality & Commitment","Capital Allocation & FPO","AGR Strategy","RPT","ESG"],
                             subs=["promoter_commitment","capital_allocation","agr_strategy","rpt","esg"],
                             qs=["{ticker} promoter management capital {year}","{company_name} AGR strategy {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian telecom.",
                           dims=["ARPU Improvement vs Guidance","EBITDA vs Consensus","Subscriber Additions","Capex vs Budget","Debt Reduction Progress"],
                           subs=["arpu_guidance","ebitda_consensus","subscriber_adds","capex_budget","debt_reduction"],
                           qs=["{ticker} ARPU EBITDA subscriber {quarter} {year}","{company_name} earnings guidance {year}"]),
         )),
    dict(folder="power",       prefix="Power",    display="Power & Utilities",           const="power",
         w=dict(fundamentals=0.19,management=0.11,business=0.10,macro=0.18,risk=0.12,valuation=0.16,technical=0.08,earnings=0.06),
         pillars=dict(
             business=dict(sys="You are a power sector analyst for Indian utilities. Expert in generation mix, PPA quality, T&D business, and DISCOM relationships.",
                           dims=["Generation Mix (Thermal/Hydro/RE)","PPA Coverage & Tenure","T&D Business","DISCOM Payment Health","Merchant vs Regulated Revenue"],
                           subs=["generation_mix","ppa_coverage","td_business","discom_health","merchant_regulated"],
                           qs=["{ticker} generation mix PPA DISCOM {year}","{company_name} T&D power business {year}","{ticker} merchant regulated revenue {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian power companies.",
                               dims=["Revenue Growth & PLF","EBITDA Margin","Net Debt/EBITDA","DSCR","RoE on Regulated Equity"],
                               subs=["revenue_plf","ebitda_margin","net_debt","dscr","regulated_roe"],
                               qs=["{ticker} PLF EBITDA DSCR {quarter} {year}","{company_name} net debt RoE power {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian power stocks.",
                            dims=["EV/EBITDA vs Peers","P/BV (Regulated)","EV/MW","Dividend Yield","P/E"],
                            subs=["ev_ebitda","pbv_regulated","ev_mw","div_yield","pe"],
                            qs=["{ticker} EV/EBITDA P/BV power valuation {year}","{company_name} EV per MW {year}"]),
             technical=dict(sys="You are a technical analyst for Indian power sector stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} power stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian power sector. Expert in coal prices, fuel linkage, electricity demand, and CERC tariff orders.",
                        dims=["Coal Price & Fuel Linkage","Electricity Demand Growth","CERC/SERC Tariff Orders","Renewable Integration","DISCOM Finances"],
                        subs=["coal_price","electricity_demand","cerc_tariff","re_integration","discom_finances"],
                        qs=["India coal price fuel linkage power {year}","India electricity demand growth {year}","CERC tariff order power {year}","DISCOM finances health India {year}"]),
             risk=dict(sys="You are a risk analyst for Indian power companies.",
                       dims=["Fuel Supply & Linkage Risk","DISCOM Payment Delays","Regulatory Tariff Risk","Plant Breakdown & Availability","Debt & Refinancing"],
                       subs=["fuel_linkage","discom_payment","tariff_risk","plant_availability","debt"],
                       qs=["{ticker} fuel linkage DISCOM payment risk {year}","{company_name} plant availability tariff risk {year}"]),
             management=dict(sys="You are a governance analyst for Indian power companies.",
                             dims=["Promoter Quality","Capital Allocation","RPT","Regulatory Track Record","ESG & Carbon Goals"],
                             subs=["promoter_quality","capital_allocation","rpt","regulatory_track","esg"],
                             qs=["{ticker} management promoter capital {year}","{company_name} ESG carbon power {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian power companies.",
                           dims=["PLF vs Normative","Revenue vs PPA Tariff","Fuel Cost Pass-through","Under-recovery","Regulatory Asset Build-up"],
                           subs=["plf_normative","revenue_tariff","fuel_passthrough","under_recovery","regulatory_asset"],
                           qs=["{ticker} PLF earnings tariff {quarter} {year}","{company_name} fuel pass-through under-recovery {year}"]),
         )),
    dict(folder="hospitality", prefix="Hosp",     display="Hospitality & Travel",        const="hospitality",
         w=dict(fundamentals=0.16,management=0.08,business=0.15,macro=0.18,risk=0.12,valuation=0.15,technical=0.09,earnings=0.07),
         pillars=dict(
             business=dict(sys="You are a hospitality analyst for Indian hotel companies and travel platforms. Expert in RevPAR, ARR, occupancy, and inventory expansion.",
                           dims=["RevPAR & ARR Trend","Occupancy Rate","Room Inventory Growth","Asset-light vs Owned Mix","Leisure vs Business Travel Mix"],
                           subs=["revpar_arr","occupancy","inventory_growth","asset_mix","travel_mix"],
                           qs=["{ticker} RevPAR ARR occupancy {quarter} {year}","{company_name} room inventory expansion {year}","{ticker} asset-light managed leased {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian hospitality companies.",
                               dims=["Revenue Growth","EBITDA Margin","Net Debt & Lease Liabilities","ROCE","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","net_debt","roce","fcf"],
                               qs=["{ticker} EBITDA margin ROCE hospitality {year}","{company_name} net debt lease {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian hospitality stocks.",
                            dims=["EV/EBITDA vs Peers","EV/Room","P/E Normalised","Price/Book","Replacement Cost"],
                            subs=["ev_ebitda","ev_room","pe_normalised","price_book","replacement_cost"],
                            qs=["{ticker} EV/EBITDA hospitality valuation {year}","{company_name} EV per room {year}"]),
             technical=dict(sys="You are a technical analyst for Indian hospitality stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} hospitality hotel stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian hospitality sector. Expert in domestic tourism, inbound FTAs, corporate travel, and event calendar.",
                        dims=["Domestic Tourism Growth","Foreign Tourist Arrivals (FTA)","Corporate Travel & MICE","Event & Wedding Season","Aviation Connectivity"],
                        subs=["domestic_tourism","fta","corporate_travel","events","aviation"],
                        qs=["India domestic tourism hospitality {year}","India foreign tourist arrivals FTA {year}","India corporate travel MICE {year}"]),
             risk=dict(sys="You are a risk analyst for Indian hospitality companies.",
                       dims=["Pandemic / Travel Disruption Risk","Oversupply in Key Markets","High Fixed Cost Structure","Rising Energy & Labour Costs","Seasonality"],
                       subs=["disruption_risk","oversupply","fixed_costs","energy_labour","seasonality"],
                       qs=["{ticker} hospitality risk oversupply {year}","{company_name} fixed costs energy labour {year}"]),
             management=dict(sys="You are a governance analyst for Indian hospitality companies.",
                             dims=["Brand Strategy & Expansion","Capital Allocation (Owned vs Managed)","RPT","Management Quality","ESG"],
                             subs=["brand_strategy","capital_allocation","rpt","management_quality","esg"],
                             qs=["{ticker} management brand expansion {year}","{company_name} capital allocation RPT {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian hospitality.",
                           dims=["RevPAR vs Guidance","EBITDA vs Consensus","Seasonality Adjustment","New Hotel Ramp-up","One-time Items"],
                           subs=["revpar_guidance","ebitda_consensus","seasonality","new_hotel_ramp","one_time"],
                           qs=["{ticker} RevPAR EBITDA earnings {quarter} {year}","{company_name} guidance hospitality {year}"]),
         )),
    dict(folder="capgoods",    prefix="CapGoods",  display="Capital Goods",              const="capgoods",
         w=dict(fundamentals=0.20,management=0.12,business=0.17,macro=0.14,risk=0.07,valuation=0.14,technical=0.09,earnings=0.07),
         pillars=dict(
             business=dict(sys="You are a capital goods analyst for Indian engineering & industrial companies. Expert in order books, product complexity, T&D equipment, railways, and industrial automation.",
                           dims=["Order Book & L1 Pipeline","Revenue Visibility (OB/Revenue)","Product Complexity & Technology","Sector Diversification (Power/Infra/Railways)","Export Revenue"],
                           subs=["order_book","revenue_visibility","product_complexity","sector_diversification","export_revenue"],
                           qs=["{ticker} order book L1 pipeline capgoods {year}","{company_name} product complexity technology {year}","{ticker} export revenue industrial {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian capital goods companies.",
                               dims=["Revenue Growth","EBITDA Margin","ROCE","Working Capital","Net Cash/Debt"],
                               subs=["revenue_growth","ebitda_margin","roce","working_capital","net_cash"],
                               qs=["{ticker} EBITDA margin ROCE capgoods {year}","{company_name} working capital net cash {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian capital goods stocks.",
                            dims=["P/E vs Peers","EV/EBITDA","EV/Order Book","Price/Book","SOTP"],
                            subs=["pe","ev_ebitda","ev_order_book","price_book","sotp"],
                            qs=["{ticker} P/E EV/EBITDA capgoods valuation {year}","{company_name} EV order book {year}"]),
             technical=dict(sys="You are a technical analyst for Indian capital goods stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} capital goods stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian capital goods sector. Expert in government capex, PLI schemes, T&D investment, and railways capex.",
                        dims=["Government Capex (Infra/Railways/Defence)","PLI Schemes & Industrial Capex","T&D & Power Equipment Demand","Export Market Demand","Private Capex Cycle"],
                        subs=["govt_capex","pli_industrial","td_power","export_market","private_capex"],
                        qs=["India government capex PLI capgoods {year}","India T&D power equipment demand {year}","India railways capex {year}"]),
             risk=dict(sys="You are a risk analyst for Indian capital goods companies.",
                       dims=["Order Cancellation Risk","Execution Delays","Input Cost Volatility","Competition from Imports","Customer Concentration"],
                       subs=["cancellation_risk","execution_delay","input_cost","import_competition","customer_concentration"],
                       qs=["{ticker} order cancellation risk {year}","{company_name} execution delay competition {year}"]),
             management=dict(sys="You are a governance analyst for Indian capital goods companies.",
                             dims=["Promoter Quality","Capital Allocation","RPT","Technology Partnerships","ESG"],
                             subs=["promoter_quality","capital_allocation","rpt","tech_partnerships","esg"],
                             qs=["{ticker} management promoter capital {year}","{company_name} technology partnership RPT {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian capital goods.",
                           dims=["Order Book Conversion to Revenue","EBITDA Margin Trend","Working Capital Improvement","Guidance vs Actual","Exceptional Items"],
                           subs=["ob_conversion","ebitda_margin","working_capital","guidance","exceptional"],
                           qs=["{ticker} earnings order conversion EBITDA {quarter} {year}","{company_name} margin guidance {year}"]),
         )),
    dict(folder="insurance",   prefix="Ins",      display="Insurance",                   const="insurance",
         w=dict(fundamentals=0.14,management=0.13,business=0.12,macro=0.12,risk=0.16,valuation=0.20,technical=0.05,earnings=0.08),
         pillars=dict(
             business=dict(sys="You are an insurance analyst for Indian life and non-life insurance companies. Expert in VNB, APE, persistency, combined ratio, and distribution.",
                           dims=["VNB Growth & VNB Margin (Life)","APE & Product Mix","Persistency Ratio","Combined Ratio (Non-life)","Distribution Channel Mix"],
                           subs=["vnb_growth","ape_mix","persistency","combined_ratio","distribution_mix"],
                           qs=["{ticker} VNB APE persistency insurance {quarter} {year}","{company_name} combined ratio non-life {year}","{ticker} distribution bancassurance agency {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian insurance companies.",
                               dims=["Embedded Value (EV) Growth","Operating RoEV","Solvency Ratio","Investment Yield","Cost Ratio"],
                               subs=["ev_growth","roev","solvency_ratio","investment_yield","cost_ratio"],
                               qs=["{ticker} embedded value EV RoEV {year}","{company_name} solvency ratio investment yield {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian insurance stocks.",
                            dims=["P/EV (Life)","VNB Multiple","P/Book (Non-life)","P/GWP","RoEV-based Fair Value"],
                            subs=["pev","vnb_multiple","pbook_nonlife","p_gwp","roev_fair_value"],
                            qs=["{ticker} P/EV VNB multiple insurance valuation {year}","{company_name} P/GWP {year}"]),
             technical=dict(sys="You are a technical analyst for Indian insurance stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} insurance stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian insurance sector. Expert in IRDAI regulations, interest rates, mortality/morbidity trends, and insurance penetration.",
                        dims=["IRDAI Regulatory Changes","Interest Rate Cycle (Investment Yield)","Insurance Penetration Expansion","Health Inflation","Reinsurance Costs"],
                        subs=["irdai_regulation","interest_rate","penetration","health_inflation","reinsurance"],
                        qs=["IRDAI regulation India insurance {year}","India insurance penetration growth {year}","India health inflation reinsurance {year}"]),
             risk=dict(sys="You are a risk analyst for Indian insurance companies.",
                       dims=["Lapse & Persistency Risk","Catastrophe & Claims Risk","Investment Portfolio Risk","Mis-selling & Regulatory Risk","Competition & Margin Pressure"],
                       subs=["lapse_risk","catastrophe_risk","investment_risk","mis_selling","competition"],
                       qs=["{ticker} lapse persistency risk insurance {year}","{company_name} catastrophe claims risk {year}"]),
             management=dict(sys="You are a governance analyst for Indian insurance companies.",
                             dims=["MD Track Record","Capital Allocation","RPT with Promoter","IRDAI Compliance","ESG"],
                             subs=["md_track_record","capital_allocation","rpt","irdai_compliance","esg"],
                             qs=["{ticker} management capital allocation insurance {year}","{company_name} IRDAI compliance {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian insurance.",
                           dims=["VNB vs Guidance","APE Growth Trend","Opex Ratio","Claims Ratio Trend","Operating Leverage"],
                           subs=["vnb_guidance","ape_growth","opex_ratio","claims_ratio","operating_leverage"],
                           qs=["{ticker} VNB APE earnings {quarter} {year}","{company_name} claims ratio guidance {year}"]),
         )),
    dict(folder="logistics",   prefix="Logist",   display="Logistics & Supply Chain",    const="logistics",
         w=dict(fundamentals=0.20,management=0.11,business=0.17,macro=0.14,risk=0.08,valuation=0.15,technical=0.10,earnings=0.05),
         pillars=dict(
             business=dict(sys="You are a logistics analyst for Indian companies. Expert in 3PL, express parcel, cold chain, freight forwarding, and warehousing.",
                           dims=["Volume Growth & Market Share","Service Mix (Express/3PL/Cold Chain)","Customer Diversification","Network & Hub Coverage","Tech/Automation Investments"],
                           subs=["volume_growth","service_mix","customer_diversification","network","tech_automation"],
                           qs=["{ticker} volume growth logistics market share {year}","{company_name} 3PL express cold chain {year}","{ticker} network hub automation {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian logistics companies.",
                               dims=["Revenue Growth","EBITDA Margin","Asset Turns & ROCE","Net Debt","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","roce","net_debt","fcf"],
                               qs=["{ticker} EBITDA margin ROCE logistics {year}","{company_name} net debt FCF {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian logistics stocks.",
                            dims=["EV/EBITDA vs Peers","P/E","EV/Revenue","Price/Book","DCF"],
                            subs=["ev_ebitda","pe","ev_revenue","price_book","dcf"],
                            qs=["{ticker} EV/EBITDA logistics valuation {year}","{company_name} P/E vs peers {year}"]),
             technical=dict(sys="You are a technical analyst for Indian logistics stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} logistics stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian logistics sector. Expert in GST impact, e-commerce growth, infrastructure investment, and freight rates.",
                        dims=["E-commerce Volumes & Growth","GST & Waybill Digitalisation","Infrastructure Investments (PM GatiShakti)","Freight Rate Cycle","Cross-border Trade"],
                        subs=["ecommerce","gst_digital","gati_shakti","freight_rates","cross_border"],
                        qs=["India e-commerce logistics growth {year}","PM GatiShakti logistics infrastructure {year}","India freight rates {year}"]),
             risk=dict(sys="You are a risk analyst for Indian logistics companies.",
                       dims=["Fuel Cost Volatility","Competition from E-commerce Captives","Asset-heavy Balance Sheet","Regulatory Compliance","Customer Concentration"],
                       subs=["fuel_cost","captive_competition","asset_heavy","regulatory","customer_concentration"],
                       qs=["{ticker} fuel cost risk logistics {year}","{company_name} competition e-commerce captive {year}"]),
             management=dict(sys="You are a governance analyst for Indian logistics companies.",
                             dims=["Promoter Track Record","Capital Allocation","RPT","Tech Strategy","ESG"],
                             subs=["promoter_track_record","capital_allocation","rpt","tech_strategy","esg"],
                             qs=["{ticker} management logistics {year}","{company_name} capital allocation tech {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian logistics.",
                           dims=["Volume vs Realization","EBITDA Margin Trend","Fuel Cost Impact","New Network Ramp-up","Guidance vs Actual"],
                           subs=["volume_realization","ebitda_margin","fuel_impact","network_ramp","guidance"],
                           qs=["{ticker} volume realization EBITDA {quarter} {year}","{company_name} fuel margin guidance {year}"]),
         )),
    dict(folder="retail",      prefix="Retail",   display="Retail & Consumer Discretionary", const="retail",
         w=dict(fundamentals=0.12,management=0.11,business=0.22,macro=0.12,risk=0.07,valuation=0.20,technical=0.11,earnings=0.05),
         pillars=dict(
             business=dict(sys="You are a retail analyst for Indian consumer discretionary and retail companies. Expert in SSSG, store expansion, omnichannel, and category mix.",
                           dims=["SSSG (Same Store Sales Growth)","Store Expansion & Productivity","Omnichannel & D2C","Category Mix & Premiumisation","Customer Loyalty Program"],
                           subs=["sssg","store_expansion","omnichannel","category_mix","loyalty"],
                           qs=["{ticker} SSSG same store sales growth retail {quarter} {year}","{company_name} store expansion omnichannel {year}","{ticker} category mix premium {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian retail companies.",
                               dims=["Revenue Growth","EBITDA Margin","Inventory Turns","Net Debt","ROCE"],
                               subs=["revenue_growth","ebitda_margin","inventory_turns","net_debt","roce"],
                               qs=["{ticker} EBITDA margin inventory turns retail {year}","{company_name} ROCE net debt {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian retail stocks.",
                            dims=["EV/EBITDA vs Peers","P/E","EV/Sales","Price/Book","DCF"],
                            subs=["ev_ebitda","pe","ev_sales","price_book","dcf"],
                            qs=["{ticker} EV/EBITDA retail valuation {year}","{company_name} P/E vs peers {year}"]),
             technical=dict(sys="You are a technical analyst for Indian retail stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} retail stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian retail sector. Expert in consumer sentiment, rural wages, inflation, and e-commerce competition.",
                        dims=["Consumer Confidence & Sentiment","Rural Wage Growth","CPI Inflation & Discretionary Spend","E-commerce Penetration","GST & Regulatory"],
                        subs=["consumer_confidence","rural_wages","inflation","ecommerce","gst"],
                        qs=["India consumer confidence sentiment retail {year}","India rural wages FMCG retail {year}","E-commerce competition traditional retail {year}"]),
             risk=dict(sys="You are a risk analyst for Indian retail companies.",
                       dims=["E-commerce Disruption","High Rentals & Real Estate Cost","Inventory Risk","Seasonality","Competition"],
                       subs=["ecommerce_disruption","rental_cost","inventory_risk","seasonality","competition"],
                       qs=["{ticker} e-commerce disruption rental risk {year}","{company_name} inventory competition retail {year}"]),
             management=dict(sys="You are a governance analyst for Indian retail companies.",
                             dims=["Promoter Quality & Vision","Capital Allocation (Owned vs Leased)","RPT","Store Format Strategy","ESG"],
                             subs=["promoter_quality","capital_allocation","rpt","store_strategy","esg"],
                             qs=["{ticker} management promoter retail {year}","{company_name} capital allocation RPT {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian retail.",
                           dims=["SSSG vs Guidance","Gross Margin Trend","Opex Leverage","New Store Ramp-up","One-time Items"],
                           subs=["sssg_guidance","gross_margin","opex_leverage","new_store","one_time"],
                           qs=["{ticker} SSSG earnings margin {quarter} {year}","{company_name} guidance retail {year}"]),
         )),
    dict(folder="media",       prefix="Media",    display="Media & Entertainment",        const="media",
         w=dict(fundamentals=0.16,management=0.11,business=0.20,macro=0.14,risk=0.07,valuation=0.16,technical=0.11,earnings=0.05),
         pillars=dict(
             business=dict(sys="You are a media analyst for Indian companies. Expert in advertising revenue, subscription, OTT streaming, box office, and live events.",
                           dims=["Ad Revenue Market Share","Subscription & OTT Growth","Box Office Performance","Live Events & IP","Digital vs Traditional Mix"],
                           subs=["ad_revenue","subscription_ott","box_office","live_events","digital_mix"],
                           qs=["{ticker} ad revenue subscription OTT {quarter} {year}","{company_name} box office live events {year}","{ticker} digital traditional media mix {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian media companies.",
                               dims=["Revenue Growth","EBITDA Margin","Content Amortisation Policy","Net Debt","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","content_amortisation","net_debt","fcf"],
                               qs=["{ticker} EBITDA margin content media {year}","{company_name} net debt FCF {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian media stocks.",
                            dims=["EV/EBITDA vs Peers","P/E","EV/Subscriber","Price/Book","SOTP"],
                            subs=["ev_ebitda","pe","ev_subscriber","price_book","sotp"],
                            qs=["{ticker} EV/EBITDA media valuation {year}","{company_name} EV per subscriber {year}"]),
             technical=dict(sys="You are a technical analyst for Indian media stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} media stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian media sector. Expert in ad market growth, GDP correlation, OTT disruption, and regulatory environment.",
                        dims=["India Ad Market Growth","GDP & Consumer Sentiment","OTT Disruption of TV","TRAI & MIB Regulation","Broadband Penetration"],
                        subs=["ad_market","gdp_sentiment","ott_disruption","trai_mib","broadband"],
                        qs=["India advertising market growth {year}","OTT disruption traditional TV India {year}","TRAI MIB media regulation {year}"]),
             risk=dict(sys="You are a risk analyst for Indian media companies.",
                       dims=["Ad Revenue Cyclicality","OTT Competition & Content Costs","Piracy","Regulatory (MIB)","Single Platform Dependence"],
                       subs=["ad_cyclicality","ott_competition","piracy","regulatory","platform_dependence"],
                       qs=["{ticker} ad revenue risk OTT competition {year}","{company_name} piracy regulatory media {year}"]),
             management=dict(sys="You are a governance analyst for Indian media companies.",
                             dims=["Promoter Quality","Capital Allocation (Content Spend)","RPT","Content Strategy","ESG"],
                             subs=["promoter_quality","capital_allocation","rpt","content_strategy","esg"],
                             qs=["{ticker} management promoter media {year}","{company_name} content strategy capital {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian media.",
                           dims=["Ad Revenue vs Guidance","Subscription Growth","Content Cost vs Budget","Operating Leverage","One-time Impairments"],
                           subs=["ad_guidance","subscription_growth","content_cost","operating_leverage","impairments"],
                           qs=["{ticker} ad subscription earnings {quarter} {year}","{company_name} content cost guidance media {year}"]),
         )),
    dict(folder="agrochem",    prefix="AgroChem", display="Agrochemicals & Fertilizers",  const="agrochem",
         w=dict(fundamentals=0.19,management=0.09,business=0.17,macro=0.17,risk=0.08,valuation=0.14,technical=0.10,earnings=0.06),
         pillars=dict(
             business=dict(sys="You are an agrochemicals analyst for Indian companies. Expert in herbicides, insecticides, fungicides, technical grade AI, and biologicals.",
                           dims=["Product Portfolio & AI Mix","Export Revenue (US/Europe/Brazil)","Registration Pipeline","Biologicals & Specialty Formulations","Domestic vs Export Mix"],
                           subs=["product_portfolio","export_revenue","registration_pipeline","biologicals","domestic_export_mix"],
                           qs=["{ticker} product portfolio AI exports agrochem {year}","{company_name} registration pipeline biologicals {year}","{ticker} domestic export agrochemical {year}"]),
             fundamentals=dict(sys="You are a financial analyst for Indian agrochemical companies.",
                               dims=["Revenue Growth","EBITDA Margin","Inventory & Working Capital","ROCE","FCF Generation"],
                               subs=["revenue_growth","ebitda_margin","inventory_working_capital","roce","fcf"],
                               qs=["{ticker} EBITDA margin inventory ROCE agrochem {year}","{company_name} FCF working capital {year}"]),
             valuation=dict(sys="You are a valuation specialist for Indian agrochem stocks.",
                            dims=["P/E vs Peers","EV/EBITDA","EV/Sales","Price/Book","Pipeline DCF"],
                            subs=["pe","ev_ebitda","ev_sales","price_book","pipeline_dcf"],
                            qs=["{ticker} P/E EV/EBITDA agrochem valuation {year}","{company_name} pipeline valuation {year}"]),
             technical=dict(sys="You are a technical analyst for Indian agrochem stocks.",
                            dims=["Trend (50/200 DMA)","RSI","MACD","Volume","Support/Resistance"],
                            subs=["trend","rsi","macd","volume","support_resistance"],
                            qs=["{ticker} agrochem stock technical {year}"]),
             macro=dict(sys="You are a macro analyst for Indian agrochemicals. Expert in kharif/rabi crop cycles, monsoon, China technical grades pricing, and global crop protection.",
                        dims=["Monsoon & Crop Season Outlook","China Technical Grade Pricing","Global Crop Protection Market","India Pesticide Regulation (CIB)","Commodity Crop Prices"],
                        subs=["monsoon_crop","china_pricing","global_market","cib_regulation","commodity_prices"],
                        qs=["India monsoon kharif rabi agrochem {year}","China agrochemical technical grade pricing {year}","Global crop protection market {year}","India CIB pesticide regulation {year}"]),
             risk=dict(sys="You are a risk analyst for Indian agrochem companies.",
                       dims=["Monsoon Failure Risk","China Dumping & Price Erosion","Patent Cliff on In-licensed AIs","Regulatory Bans (CIB)","Inventory Build-up Risk"],
                       subs=["monsoon_risk","china_dumping","patent_cliff","regulatory_ban","inventory_risk"],
                       qs=["{ticker} monsoon risk China dumping agrochem {year}","{company_name} patent cliff CIB ban {year}"]),
             management=dict(sys="You are a governance analyst for Indian agrochem companies.",
                             dims=["Promoter Quality","R&D Pipeline Strategy","Capital Allocation","RPT","ESG & Pesticide Safety"],
                             subs=["promoter_quality","rd_pipeline","capital_allocation","rpt","esg"],
                             qs=["{ticker} management promoter R&D agrochem {year}","{company_name} capital allocation ESG {year}"]),
             earnings=dict(sys="You are an earnings analyst for Indian agrochem.",
                           dims=["Domestic vs Export Volume","EBITDA Margin Trend","Inventory Correction Impact","New Product Revenue","Guidance vs Actual"],
                           subs=["domestic_export_volume","ebitda_margin","inventory_correction","new_product","guidance"],
                           qs=["{ticker} volume exports earnings {quarter} {year}","{company_name} EBITDA guidance agrochem {year}"]),
         )),
]

# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

PILLAR_ORDER = ["business","fundamentals","valuation","technical","macro","risk","management","earnings"]

def agent_file(sector: dict, pillar: str) -> str:
    p    = sector["prefix"]
    fld  = sector["folder"]
    disp = sector["display"]
    data = sector["pillars"][pillar]
    cls  = f"{p}{pillar.capitalize()}Agent"
    dims = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(data["dims"]))
    return f'''"""
sectors/{fld}/{pillar}.py
{"=" * (len(fld) + len(pillar) + 14)}
{pillar.capitalize()} sub-agent for the {disp} sector.

Data dimensions covered:
{dims}
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.{fld} import {pillar} as P


class {cls}(BaseAgent):
    """Analyses {pillar} dimensions for {disp} companies."""

    @property
    def agent_name(self) -> str:
        return "{pillar}"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
'''


def registry_file(sector: dict) -> str:
    fld   = sector["folder"]
    p     = sector["prefix"]
    disp  = sector["display"]
    w     = sector["w"]
    lines_import = "\n".join(
        f"from core.sectors.{fld}.{pillar} import {p}{pillar.capitalize()}Agent"
        for pillar in PILLAR_ORDER
    )
    lines_agents = "\n".join(
        f'    "{pillar}": {p}{pillar.capitalize()}Agent(),'
        for pillar in PILLAR_ORDER
    )
    lines_weights = "\n".join(
        f'    "{pillar}": {w[pillar]},'
        for pillar in PILLAR_ORDER
    )
    return f'''"""
core/sectors/{fld}/registry.py
{"=" * (len(fld) + 24)}
Agent registry for the {disp} sector.

Pillar weights:
{chr(10).join(f"  {p:<14}  {w[p]}" for p in PILLAR_ORDER)}
            ─────
Total           {sum(w.values()):.2f}
"""

{lines_import}

AGENTS: dict = {{
{lines_agents}
}}

WEIGHTS: dict[str, float] = {{
{lines_weights}
}}

LEGACY_AGENT_ALIASES: dict[str, str] = {{}}
'''


def agents_shim_file(sector: dict) -> str:
    fld  = sector["folder"]
    p    = sector["prefix"]
    disp = sector["display"]
    lines_import = "\n".join(
        f"from core.sectors.{fld}.{pillar} import {p}{pillar.capitalize()}Agent"
        for pillar in PILLAR_ORDER
    )
    lines_all = "\n".join(
        f'    "{p}{pillar.capitalize()}Agent",'
        for pillar in PILLAR_ORDER
    )
    return f'''"""
sectors/{fld}/agents.py
{"=" * (len(fld) + 13)}
Backward-compatibility shim for the {disp} sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.{fld}.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

{lines_import}

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
{lines_all}
]
'''


def graph_file(sector: dict) -> str:
    fld   = sector["folder"]
    const = sector["const"]
    disp  = sector["display"]
    n_pillars = len(PILLAR_ORDER)
    return f'''"""
sectors/{fld}/graph.py
{"=" * (len(fld) + 13)}
LangGraph StateGraph for the {disp} sector.

{n_pillars}-pillar framework:
{chr(10).join(f"  {p} ({sector['w'][p]})" for p in PILLAR_ORDER)}

Topology: START → resolve_ticker → input_rail
          → [Send fan-out × {n_pillars}] → run_agent (parallel)
          → aggregate → END
"""

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy  # type: ignore[no-redef]

from core.graphs.nodes import (
    make_aggregate_node,
    make_dispatch_fn,
    make_input_rail_node,
    make_resolve_ticker_node,
    make_run_agent_node,
)
from core.graphs.state import GraphState
from core.sectors.{fld}.registry import AGENTS, WEIGHTS

SECTOR = "{const}"

_resolve_ticker = make_resolve_ticker_node(SECTOR)
_input_rail     = make_input_rail_node(SECTOR)
_run_agent      = make_run_agent_node(AGENTS, SECTOR)
_aggregate      = make_aggregate_node(WEIGHTS, SECTOR)
_dispatch       = make_dispatch_fn(list(AGENTS.keys()))

_workflow = StateGraph(GraphState)

_workflow.add_node("resolve_ticker", _resolve_ticker)
_workflow.add_node("input_rail",     _input_rail)
_workflow.add_node("run_agent",      _run_agent, retry=RetryPolicy(max_attempts=2))
_workflow.add_node("aggregate",      _aggregate)

_workflow.add_edge(START,            "resolve_ticker")
_workflow.add_edge("resolve_ticker", "input_rail")
_workflow.add_conditional_edges("input_rail", _dispatch)
_workflow.add_edge("run_agent",  "aggregate")
_workflow.add_edge("aggregate",  END)

graph = _workflow.compile()
graph.name = "{const}"
'''


def prompt_file(sector: dict, pillar: str) -> str:
    fld  = sector["folder"]
    disp = sector["display"]
    data = sector["pillars"][pillar]

    sys_prompt  = data["sys"]
    dims        = data["dims"]
    subs        = data["subs"]
    queries     = data["qs"]

    dims_block = "\n\n".join(
        f"{i+1}. **{d}** — Assess and score this dimension for {{ticker}} ({{company_name}})."
        for i, d in enumerate(dims)
    )

    sub_scores_json = "\n".join(
        f'    "{s}": <float>,'
        for s in subs
    )

    queries_block = "\n".join(
        f'    "{q}",'
        for q in queries
    )

    # Build the file using string concat to avoid f-string brace escaping issues
    part1 = (
        '"""\n'
        f'prompts/{fld}/{pillar}.py\n'
        f'{"=" * (len(fld) + len(pillar) + 10)}\n'
        f'Prompt templates for the {disp} {pillar.capitalize()} agent.\n'
        f'Framework source: sector_analysis_v4_final.html — {disp} > {pillar.capitalize()} pillar\n'
        '"""\n\n'
        'SYSTEM_PROMPT = """'
        + sys_prompt +
        '"""\n\n'
        'ANALYSIS_PROMPT = """Analyse the '
        + pillar.capitalize() +
        ' outlook for Indian ' + disp.lower() + ' company: **{ticker}** ({company_name}).\n\n'
        'Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):\n\n'
        + dims_block + '\n\n'
        'Context / recent data snippets:\n'
        '{context}\n\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        '  "agent": "' + pillar + '",\n'
        '  "ticker": "{ticker}",\n'
        '  "overall_score": <float 0.0-1.0>,\n'
        '  "sub_scores": {\n'
        + sub_scores_json + '\n'
        '  },\n'
        '  "key_positives": [<string>, ...],\n'
        '  "key_risks": [<string>, ...],\n'
        '  "summary": "<2-3 sentence narrative>",\n'
        '  "data_freshness": "<date of most recent data point used>"\n'
        '}\n'
        '"""\n\n'
        'CONTEXT_SEARCH_QUERIES = [\n'
        + queries_block + '\n'
        ']\n'
    )
    return part1


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).parent

    total = 0
    for sector in SECTORS:
        fld = sector["folder"]
        print(f"\n[{fld}] Generating files...")

        sector_dir = root / "core" / "sectors" / fld
        prompt_dir = root / "core" / "config" / "prompts" / fld
        sector_dir.mkdir(parents=True, exist_ok=True)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        # __init__.py files
        (sector_dir / "__init__.py").write_text("", encoding="utf-8")
        (prompt_dir / "__init__.py").write_text("", encoding="utf-8")
        total += 2

        # 8 agent files
        for pillar in PILLAR_ORDER:
            path = sector_dir / f"{pillar}.py"
            path.write_text(agent_file(sector, pillar), encoding="utf-8")
            print(f"  + {path.relative_to(root)}")
            total += 1

        # registry.py
        path = sector_dir / "registry.py"
        path.write_text(registry_file(sector), encoding="utf-8")
        print(f"  + {path.relative_to(root)}")
        total += 1

        # agents.py (shim)
        path = sector_dir / "agents.py"
        path.write_text(agents_shim_file(sector), encoding="utf-8")
        print(f"  + {path.relative_to(root)}")
        total += 1

        # graph.py
        path = sector_dir / "graph.py"
        path.write_text(graph_file(sector), encoding="utf-8")
        print(f"  + {path.relative_to(root)}")
        total += 1

        # 8 prompt files
        for pillar in PILLAR_ORDER:
            path = prompt_dir / f"{pillar}.py"
            path.write_text(prompt_file(sector, pillar), encoding="utf-8")
            print(f"  + {path.relative_to(root)}")
            total += 1

    print(f"\nDone — {total} files generated across {len(SECTORS)} sectors.")


if __name__ == "__main__":
    main()
