# Frontend/Backend Field Audit Report
**Date:** 2026-04-08
**Scope:** Verification of new recommendation fields in database, API, and frontend components

---

## Executive Summary

✅ **GOOD NEWS:** All four new fields are properly implemented throughout the stack.

⚠️ **FINDINGS:** 
1. `position_note` exists but is NOT displayed (intentional - superseded by position_rationale)
2. Documentation could be enhanced
3. No blocking issues found

---

## NEW FIELDS STATUS

| Field | DB | Backend | API | Frontend | Status |
|-------|----|---------|----|----------|--------|
| `trailing_activation_price` | ✅ | ✅ | ✅ | ✅ | PASS |
| `trailing_distance_pct` | ✅ | ✅ | ✅ | ✅ | PASS |
| `position_rationale` | ✅ | ✅ | ✅ | ✅ | PASS |
| `position_pct` | ✅ | ✅ | ✅ | ✅ | PASS |

---

## DETAILED FINDINGS

### 1. DATABASE SCHEMA ✅

**Migration Status:** `core/database.py` lines 425-445
- `trailing_activation_price` → REAL DEFAULT 0
- `trailing_distance_pct` → REAL DEFAULT 0  
- `position_rationale` → TEXT DEFAULT ''
- Both `daily_recommendation_items` and `published_recommendation_items` tables updated

**Schema Initialization:** `_init_tables()` includes all fields
**Data Insertion:** `_insert_recommendation_items()` (lines 914-976) properly parameterizes all fields

### 2. BACKEND GENERATION ✅

**Location:** `pipeline/agents.py` (Layer 5 Synthesis, lines 1080-1149)

**trailing_activation_price & trailing_distance_pct:**
- Lines 1114-1115: Extracted from trade object if is_quality=True
- Assigned from strategy configuration

**position_pct & position_rationale:**
- Lines 1085-1093: Called via `_suggest_position_pct()` function
- Lines 1128-1129: Stored in recommendation dict

**Multi-factor Model (_suggest_position_pct(), lines 1181-1256):**
- Base allocation by score (3-8%)
- Confidence multiplier (0.70x - 1.20x)
- Volatility adjustment (0.70x - 1.10x)
- Risk flags impact (0.60x - 0.80x per flag count)
- R:R ratio multiplier (0.85x - 1.15x)
- Strategy type adjustment (0.90x for swing)
- Market regime multiplier (0.50x - 1.00x)
- Final clamping: max(2%, min(10%))
- Chinese rationale string built with all factors

### 3. API ENDPOINTS ✅

**All recommendation endpoints use:** `SELECT * FROM [table]`
- `GET /api/recommendations/today`
- `GET /api/recommendations/{ref_date}`
- `GET /api/recommendations/{market}/today`
- `GET /api/recommendations/{market}/{ref_date}`

**No field filtering:** Items returned as `dict(i)` with all columns

### 4. DATABASE PUBLISHING ✅

**publish_recommendations()** (lines 550-577):
- Calls same `_insert_recommendation_items()` method
- All new fields properly copied from daily to published table
- No field stripping or filtering

### 5. FRONTEND DISPLAY ✅

**RecCard.jsx Component:**

**Trailing Stop Section (lines 171-207):**
- ✅ Displays `trailing_activation_price` in portfolio currency
- ✅ Displays `trailing_distance_pct` as percentage
- ✅ Shows profit % reached (handles SHORT case correctly)
- ✅ Only shows if both values > 0

**Position Rationale (lines 208-213):**
- ✅ Displays `position_rationale` Chinese string
- ✅ Conditional display (only if exists)
- ✅ Proper styling with icon

**Position Percentage (lines 625-632):**
- ✅ Displays `position_pct`
- ✅ Color-coded: emerald (>=6%), amber (4-5%), rose (<4%)
- ✅ Shown in header row

### 6. SHORT POSITION HANDLING ✅

**Trailing Stop Profit Calc (lines 183-188):**
```
SHORT: (entry - activation) / (entry - tp) * 100
LONG:  (activation - entry) / (tp - entry) * 100
```
✅ Mathematically correct for both directions

### 7. PAGE LEVEL INTEGRATION ✅

**RecommendationsPage.jsx:**
- Passes full item object to RecCard
- No filtering of fields

**DashboardPage.jsx:**
- Compact preview shows essential fields
- Full details available via link to RecCard

---

## ISSUES & NOTES

### position_note Field
- **Status:** In database (not removed, preserved for audit)
- **Display:** Not shown in frontend (intentional)
- **Reason:** Superseded by position_rationale (better content)
- **Assessment:** ✅ Correct design decision

### Documentation
- `API_FIELDS_MAPPING.md` exists but incomplete
- Missing the 4 new fields in mapping
- **Recommendation:** Update documentation

---

## VERIFICATION CHECKLIST

- ✅ Trailing activation price displays in correct currency ($, HK$)
- ✅ Trailing distance shown as percentage (value * 100)
- ✅ Position rationale shows Chinese explanation
- ✅ Position pct color-coded correctly
- ✅ All fields stored in daily_recommendation_items
- ✅ All fields copied to published_recommendation_items
- ✅ API returns all fields without filtering
- ✅ Frontend receives all fields
- ✅ Frontend displays all relevant fields
- ✅ SHORT position calculations verified
- ✅ No data loss in publishing pipeline
- ✅ Migration handles existing databases

---

## CONCLUSION

🟢 **AUDIT RESULT: PASS**

All four new backend fields are correctly implemented across:
- Database schema (with migrations)
- Backend generation (multi-factor model)
- Data storage (both daily and published tables)
- API transport (no filtering)
- Frontend display (with appropriate styling)
- Special cases (SHORT positions, currencies)

**No blocking issues. System is production-ready.**

