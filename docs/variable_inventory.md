# Variable Inventory: Predicting College Closures and Financial Distress

Reference: Kelchen, Ritter, Webber (2025). FEDS 2025-003.

Cross-referenced against Table A1 (descriptive statistics), Table 6 (feature importance), and Sections III-IV (data sources, methodology).

## Column Definitions

- **Variable Name**: Human-readable name matching paper terminology
- **Variable Category**: Grouping per Table A1 and paper structure
- **Source**: IPEDS, PEPS, College Scorecard, Federal Student Aid, BEA, Census SAIPE, BLS LAUS, or Derived
- **IPEDS Survey Component**: For IPEDS variables only
- **Derived vs Raw**: "Raw" if directly from source, "Derived" if computed from other variables
- **Transformations**: Lags (L2=t-2, L3=t-3, etc.), YOY % change, ratios, quartile bins, log, etc.
- **Model Tier**: "Select" (used in limited/LASSO-selected models), "All" (only in full XGBoost with all controls), "Both"
- **Years Required**: Time range the paper uses
- **Notes**: Special handling details

## Outcome Variables

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Closed in year t | Outcome | PEPS | — | Raw | None | Both | 1996–2023 | Main campus closures only (OPEID ending "00"); PEPS data through Nov 2023; matched to IPEDS UnitID |
| Closed within 3 years | Outcome | PEPS | — | Derived | Forward-looking 3yr window | Both | 1996–2023 | Primary outcome for closure models; 1,671 total closures in panel |
| 10% enrollment decline vs 5yr high | Outcome | IPEDS | Fall Enrollment / 12-Month Enrollment | Derived | Compare current to max of prior 5 years | Both | 2002–2023 | Binary indicator; requires 5yr lookback |
| 10% revenue decline vs 5yr high | Outcome | IPEDS | Finance | Derived | Compare current to max of prior 5 years (CPI-adjusted) | Both | 2002–2023 | Binary indicator; CPI-adjusted to 2023 dollars |
| Persistently negative operating margin (3 of 5 yrs) | Outcome | IPEDS | Finance | Derived | Rolling 5yr window, flag if >=3 negative | Both | 2002–2023 | Binary indicator |
| HCM Level 2 status | Outcome | College Scorecard | — | Raw | None | Both | 2002–2023 | Heightened Cash Monitoring; also used as predictor |

## Accountability Metrics

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| HCM Level 2 indicator | Accountability | College Scorecard | — | Raw | L2, L3 | Both | 2002–2023 | Binary; most serious federal monitoring level; 1% of never-closed institutions flagged |
| Financial Responsibility Composite (FRC) score | Accountability | Federal Student Aid | — | Raw | L2, L3 | Both | 2006–2020 | Continuous score; only 37% of never-closed have data; 5% of closed have data; private institutions only |

## Financial Performance

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Operating margin | Financial Performance | IPEDS | Finance | Derived | L2, L3; quartile bins in OLS binned | Both | 2002–2023 | (Total revenue - total expenses) / total revenue; 79% data coverage (never-closed); mean 4.1% |
| Persistently negative operating margin | Financial Performance | IPEDS | Finance | Derived | Rolling 5yr window | Both | 2002–2023 | Binary; 15.7% of never-closed vs 35.5% of closed (2yr prior) |
| YOY change, operating margin | Financial Performance | IPEDS | Finance | Derived | L2, L3; percentage point change | Both | 2002–2023 | 77% data coverage |
| Days cash on hand (DCOH) | Financial Performance | IPEDS | Finance | Derived | L2, L3; quartile bins in OLS binned | Both | 2002–2023 | Cash and short-term investments / (total expenses / 365); highly skewed; winsorized at 2.5% |
| YOY change, DCOH | Financial Performance | IPEDS | Finance | Derived | L2, L3 | Both | 2002–2023 | 99% coverage |
| Debt ($mil) | Financial Performance | IPEDS | Finance | Derived | L2, L3; log transform in XGBoost All | Both | 2002–2023 | CPI-adjusted to 2023$; only 59% coverage (never-closed); 4% for closed |
| EBIDA ($mil) | Financial Performance | IPEDS | Finance | Derived | L2, L3; log transform in XGBoost All | Both | 2002–2023 | Earnings before interest, depreciation, amortization; 79% coverage; CPI-adjusted |
| Debt to EBIDA | Financial Performance | IPEDS | Finance | Derived | L2 | Both | 2002–2023 | 54% coverage |
| Debt to assets (leverage) | Financial Performance | IPEDS | Finance | Derived | L2, L3; YOY change; quartile bins | Both | 2002–2023 | 75% coverage; mean ~2400 for never-closed |
| YOY change, debt to assets | Financial Performance | IPEDS | Finance | Derived | L2, L3 | Both | 2002–2023 | 74% coverage; labeled "DBT asst PP change" in Table 6 |
| Unrestricted net assets ($mil) | Financial Performance | IPEDS | Finance | Derived | L2, L3; log transform in XGBoost All; quartile bins | Both | 2002–2023 | CPI-adjusted; 93% coverage; mean $72.2M never-closed vs $2.7M closed |

## Revenue

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Total revenue ($mil) | Revenue | IPEDS | Finance | Raw | L2, L3; log in some models; CPI-adjusted | Both | 2002–2023 | CPI-adjusted to 2023$; 92% coverage |
| YOY change, total revenue | Revenue | IPEDS | Finance | Derived | L2, L3, L4 | Both | 2002–2023 | Nominal % change (not CPI-adjusted); 92% coverage; L4 appears in XGBoost All |
| Revenue 10% lower than 5yr high | Revenue | IPEDS | Finance | Derived | Rolling 5yr lookback | Both | 2002–2023 | Binary; 40% of never-closed; "Yes" for 86% of closed |
| Tuition / total revenue | Revenue | IPEDS | Finance | Derived | L2, L3; quartile bins | Both | 2002–2023 | 93% coverage; mean 48% never-closed vs 77% closed |
| Auxiliary / total revenue | Revenue | IPEDS | Finance | Derived | L2, L3; quartile bins | Both | 2002–2023 | 75% coverage; mean 7% |
| Investment revenue / total revenue | Revenue | IPEDS | Finance | Derived | L2 | Both | 2002–2023 | 93% coverage; mean 3% |
| Gifts, grants, contracts / total revenue | Revenue | IPEDS | Finance | Derived | L2, L3, L5; quartile bins | Both | 2002–2023 | 82% coverage; labeled "Revenue % GGC" in Table 6 |

## Expenses

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Total expenses ($mil) | Expenses | IPEDS | Finance | Raw | L2, L3; log transform; CPI-adjusted | Both | 2002–2023 | CPI-adjusted to 2023$; 93% coverage |
| Instructional / total expenses | Expenses | IPEDS | Finance | Derived | L2, L3, L4; quartile bins | Both | 2002–2023 | Labeled "EAP % Instruction" in Table 6; 93% coverage; mean 40% |
| Scholarships / total expenses | Expenses | IPEDS | Finance | Derived | L2, L3; quartile bins | Both | 2002–2023 | 93% coverage; mean 16% |
| Interest / total expenses | Expenses | IPEDS | Finance | Derived | L2 | Both | 2002–2023 | 79% coverage; mean 1% |
| Depreciation / total expenses | Expenses | IPEDS | Finance | Derived | L2, L3; quartile bins | Both | 2002–2023 | 79% coverage; mean 5% |

## Staff

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Total staff | Staff | IPEDS | Human Resources | Raw | L2; log in some models | Both | 2002–2023 | 94% coverage; mean 689 never-closed vs 195 closed |
| YOY change, total staff | Staff | IPEDS | Human Resources | Derived | L2 | Both | 2002–2023 | Labeled "Total EAP % change" in Table 6; 91% coverage |
| Instructional / total staff | Staff | IPEDS | Human Resources | Derived | L2 | Both | 2002–2023 | 89% coverage; mean 50% |
| Full-time / total staff | Staff | IPEDS | Human Resources | Derived | L2, L3; quartile bins | Both | 2002–2023 | Labeled "EAP % ft" in Table 6; 94% coverage; mean 66% |

## Enrollment

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Total enrollment (12-month) | Enrollment | IPEDS | 12-Month Enrollment | Raw | L2, L3; log transform | Both | 2002–2023 | 95% coverage; mean 5,190 never-closed vs 1,257 closed |
| YOY change, 12-month enrollment | Enrollment | IPEDS | 12-Month Enrollment | Derived | L2, L3 | Both | 2002–2023 | Labeled "Enroll % change" in Table 6; 92% coverage; top feature in XGBoost Continuous |
| Undergraduate / total enrollment | Enrollment | IPEDS | Fall Enrollment | Derived | L2 | Both | 2002–2023 | 93% coverage; mean 87% never-closed vs 100% closed |
| Enrollment 10% lower than 5yr high | Enrollment | IPEDS | 12-Month Enrollment | Derived | Rolling 5yr lookback | Both | 2002–2023 | Binary; 41% never-closed vs 93% closed; labeled "Five % Enroll 5yr" in OLS Lasso |
| 3 consecutive years of >5% enrollment drops | Enrollment | IPEDS | 12-Month Enrollment | Derived | Rolling 3yr lookback | Both | 2002–2023 | Binary; 3% never-closed vs 21% closed; labeled "Ten % Enroll 5yr" variant in models |

## Institutional Characteristics

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Sector (public, private nonprofit, private for-profit) | Institutional Characteristics | IPEDS / College Scorecard | Institutional Characteristics | Raw | Categorical dummies | Both | 2002–2023 | Time-invariant W_i; closure models restricted to private institutions |
| Predominant degree level (2-year vs 4-year) | Institutional Characteristics | College Scorecard / IPEDS | Institutional Characteristics | Raw | Binary | Both | 2002–2023 | Supplemented with Carnegie classifications where missing; ~20% missing |
| PNFP 4yr indicator | Institutional Characteristics | Derived | — | Derived | Binary interaction | Both | 2002–2023 | Private nonprofit four-year; appears prominently in Table 6 (1.8% gain XGBoost All) |
| State | Institutional Characteristics | IPEDS | Institutional Characteristics | Raw | State fixed effects (50 + DC) | All | 2002–2023 | Used in XGBoost All Controls; 50 states + DC |
| OPEID | Institutional Characteristics | PEPS / Federal Student Aid | — | Raw | Identifier | — | 1996–2023 | Unit of analysis for closure; aggregated from UnitID |
| UnitID | Institutional Characteristics | IPEDS | Institutional Characteristics | Raw | Identifier | — | 2002–2023 | IPEDS institution identifier; linked to OPEID |

## County Controls

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Population (mil) | County Controls | BEA | — | Raw | L2; log in some models | All | 1967–2022 | County-level; 92% coverage; mean 1.1M never-closed |
| Personal income per capita ($) | County Controls | BEA | — | Raw | L2 | All | 1967–2022 | County-level; 92% coverage; mean $46,671 |
| Unemployment rate | County Controls | BLS LAUS | — | Raw | L2 | All | 1990–2022 | County-level; 95% coverage |
| Poverty rate | County Controls | Census SAIPE | — | Raw | L2 | All | 1997–2022 | County-level; 93% coverage; mean 15% |

## Additional Variables in XGBoost All Controls (from Table 6)

These variables appear in the XGBoost (All Controls) feature importance list but are not separately enumerated in Table A1. They represent additional lags, transformations, or quartile-binned versions of base variables above.

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| Salaries % staff | Staff / Expenses | IPEDS | Finance / Human Resources | Derived | L2 | All | 2002–2023 | Salary expenses as share of total staff; 1.6% gain in XGBoost All |
| L4 Revenue % change | Revenue | IPEDS | Finance | Derived | L4 lag of YOY revenue change | All | 2002–2023 | 1.8% gain in XGBoost All |
| L4 Expenses % Instruction | Expenses | IPEDS | Finance | Derived | L4 of instructional/total expenses | All | 2002–2023 | 1.1% gain in XGBoost All |
| L3 Revenue % change | Revenue | IPEDS | Finance | Derived | L3 lag of YOY revenue change | All | 2002–2023 | 1.6% gain in XGBoost Continuous |
| L3 Total EAP % change | Staff | IPEDS | Human Resources | Derived | L3 lag of YOY staff change | All | 2002–2023 | 2.0% gain in XGBoost All |
| L3 Expenses % Instruction | Expenses | IPEDS | Finance | Derived | L3 of instructional/total expenses | All | 2002–2023 | 2.3% gain in XGBoost Continuous |
| L3 Revenue % Tuition | Revenue | IPEDS | Finance | Derived | L3 of tuition/total revenue | All | 2002–2023 | 2.4% gain in XGBoost Continuous |
| L3 OP Margin | Financial Performance | IPEDS | Finance | Derived | L3 of operating margin | All | 2002–2023 | 2.6% gain in XGBoost Continuous |
| L3 Log Unrestricted Assets | Financial Performance | IPEDS | Finance | Derived | L3 of log(unrestricted net assets) | All | 2002–2023 | 2.4% gain in XGBoost Continuous |
| L3 Log expenses | Expenses | IPEDS | Finance | Derived | L3 of log(total expenses) | All | 2002–2023 | 2.0% gain in XGBoost Continuous |
| L3 Log Enroll 12mo | Enrollment | IPEDS | 12-Month Enrollment | Derived | L3 of log(12-month enrollment) | All | 2002–2023 | 2.0% gain in XGBoost Continuous |
| L3 FRC Score | Accountability | Federal Student Aid | — | Raw | L3 lag | All | 2006–2020 | 1.3% gain in XGBoost All |
| L3 Log EBITDA | Financial Performance | IPEDS | Finance | Derived | L3 of log(EBIDA) | All | 2002–2023 | TBD exact coverage |
| L5 Revenue % GGC | Revenue | IPEDS | Finance | Derived | L5 of gifts,grants,contracts/total revenue | All | 2002–2023 | 1.2% gain in XGBoost All |
| L3 DCOH change | Financial Performance | IPEDS | Finance | Derived | L3 of YOY change in DCOH | All | 2002–2023 | Appears in OLS Lasso results |
| L3 DBT asst PP change | Financial Performance | IPEDS | Finance | Derived | L3 of YOY change in debt-to-assets | All | 2002–2023 | 0.2% standardized coeff in OLS Lasso |

## Quartile-Binned Variables (OLS Binned Models)

In the OLS binned models, continuous variables are converted to quartile bins (1stQ, 2ndQ, 3rdQ, 4thQ) plus a "missing" bin. These appear prominently in Table 6 OLS (Binned) results.

| Variable Name | Variable Category | Source | IPEDS Survey Component | Derived vs Raw | Transformations | Model Tier | Years Required | Notes |
|---|---|---|---|---|---|---|---|---|
| EAP % Instruction (1stQ–4thQ) | Expenses | IPEDS | Finance | Derived | L2; quartile bins | Select | 2002–2023 | Top predictor in OLS Binned (4thQ: 0.8% std coeff) |
| DCOH (1stQ–4thQ) | Financial Performance | IPEDS | Finance | Derived | L2, L3; quartile bins | Select | 2002–2023 | 1stQ L2: -1.1% std coeff in OLS Binned |
| Log Unrestricted Assets (1stQ–4thQ) | Financial Performance | IPEDS | Finance | Derived | L2, L3; quartile bins | Select | 2002–2023 | 1stQ L2: -2.7% std coeff in OLS Binned |
| Debt to Assets (1stQ) | Financial Performance | IPEDS | Finance | Derived | L2, L3; quartile bins | Select | 2002–2023 | L2: 2.9% std coeff in OLS Binned |
| Depreciation % Expenses (1stQ–2ndQ) | Expenses | IPEDS | Finance | Derived | L2, L3; quartile bins | Select | 2002–2023 | Appears in OLS Binned |
| Revenue % Auxiliary (1stQ) | Revenue | IPEDS | Finance | Derived | L3; quartile bins | Select | 2002–2023 | 0.9% std coeff in OLS Binned |
| OP Margin PP change (1stQ) | Financial Performance | IPEDS | Finance | Derived | L3; quartile bins | Select | 2002–2023 | 0.5% std coeff in OLS Binned |
| Enroll % change (1stQ) | Enrollment | IPEDS | 12-Month Enrollment | Derived | L2; quartile bins | Select | 2002–2023 | 3.2% gain in XGBoost Binned (top feature) |
| Revenue % GGC (1stQ) | Revenue | IPEDS | Finance | Derived | L2, L3; quartile bins | Select | 2002–2023 | 2.6% gain in XGBoost Binned |
| Salaries % Staff (1stQ) | Staff / Expenses | IPEDS | Finance / Human Resources | Derived | L2; quartile bins | Select | 2002–2023 | 2.0% gain in XGBoost Binned |
| EAP % ft (1stQ) | Staff | IPEDS | Human Resources | Derived | L2, L3; quartile bins | Select | 2002–2023 | Full-time share; 1.1% gain in XGBoost Binned |
| Revenue % Tuition (4thQ) | Revenue | IPEDS | Finance | Derived | L2; quartile bins | Select | 2002–2023 | 1.0% gain in XGBoost Binned |

## Summary Statistics

| Metric | Value |
|---|---|
| Total base variables (Table A1 rows) | ~42 |
| Total with lags/transforms (Table 6 features) | ~70+ |
| Data sources represented | 7 (IPEDS, PEPS, College Scorecard, Federal Student Aid, BEA, Census SAIPE, BLS LAUS) |
| Panel period | 2002–2023 (some sources from 1967/1990/1996) |
| Total observations (never-closed) | 110,559 |
| Total closed institution observations | 1,263 |
| Total institutions in panel | 8,633 |
| Total closures | 1,671 |

## Key Notes on Transformations

1. **Lag structure**: Primary lags are L2 (t-2) and L3 (t-3). The XGBoost All Controls model adds L4 and L5 for select variables. Lags start at t-2 because IPEDS data for year t is not available until ~t+1.
2. **CPI adjustment**: Dollar values (revenue, expenses, debt, assets, EBIDA) adjusted to 2023 dollars. YOY percent changes use nominal values.
3. **Winsorization**: Variables with skewed distributions winsorized at 2.5% level.
4. **Log transforms**: Applied to dollar values and counts (expenses, EBIDA, unrestricted assets, enrollment, staff) in continuous models.
5. **Quartile bins**: Used in OLS binned models; include a "missing" category to handle systematic missingness. Bins defined across all institution-years.
6. **Missing data**: Substantial and systematic. Debt, assets, and leverage variables have 40-60% missing rates. Financial data most affected for closed institutions. XGBoost handles missingness natively; OLS models use binned "missing" indicators.

## TBD / Flagged Items

- [ ] Exact IPEDS table names for each Finance sub-variable (F1A vs F2 vs F3 depending on GASB/FASB reporting)
- [ ] Additional institutional characteristics used only in XGBoost All Controls but not enumerated in Table A1 or Table 6
- [ ] Endowment variable mentioned in Section III.A bullet list but absent from Table A1 — may not have been included in final models
- [ ] Salaries as a separate expense category vs "Salaries % staff" — verify whether this is salary expenditures / total staff count or salary expenses / total expenses
- [ ] Year fixed effects: excluded from preferred models but tested; verify they are not needed as a variable
- [ ] Cohort Default Rates (CDR): collected but explicitly excluded from models per Section III.C
