# kb-agent

AWS Bedrock AgentCore knowledge-base agent.

## מאגר מקטים / ספקים (S3)

הנתונים המנורמלים (UTF-8) נטענים בזמן עליית הקונטיינר מ־S3 אם מוגדר באקט; אחרת מהקבצים בתיקיית הסוכן.

### מבנה באקט

ברירת מחדל לקידומית: `rehab-data/v1/` (ניתן לשינוי ב־`REHAB_DATA_S3_PREFIX`).

| מפתח S3 | תיאור |
|----------|--------|
| `rehab-data/v1/sku_catalog.csv` | פרוט מקטים |
| `rehab-data/v1/suppliers.csv` | ספקים בעלי הסכם פעיל |
| `rehab-data/v1/supplier_sku_links.csv` | קישור מקט ↔ ספק (שדה `is_active` = כן לשורות פעילות) |

מפרט JSON: `rehab_s3_layout.json`.

### הכנת קבצים והעלאה

1. שים את ה־CSV הגולמיים ב־`raw_csvs/` והרץ `python convert_csvs.py` (יוצר את שלושת הקבצים המנורמלים בתיקייה).
2. העלה ל־S3: `python sync_rehab_data_to_s3.py --bucket YOUR_BUCKET [--prefix rehab-data/v1]`

### משתני סביבה בסוכן (AgentCore / Dockerfile)

- `REHAB_DATA_S3_BUCKET` — שם הבאקט (חובה לשימוש ב־S3).
- `REHAB_DATA_S3_PREFIX` — קידומית (אופציונלי, ברירת מחדל `rehab-data/v1`).
- `REHAB_DATA_S3_REGION` — אזור הבאקט אם שונה מ־`AWS_REGION` (אופציונלי).

### הרשאות IAM

לתפקיד הריצה של AgentCore (`AgentCoreRuntimeRole`) הוסף מדיניות המאפשרת `s3:GetObject` על:

`arn:aws:s3:::YOUR_BUCKET/rehab-data/v1/*`

### כלים בסוכן

- `find_suppliers_for_need` — חיפוש מהיר "מי נותן שירות".
- `lookup_rehab_catalog` — כל השדות מהטבלאות (מקט מלא, ספק מלא, שורות קישור).
