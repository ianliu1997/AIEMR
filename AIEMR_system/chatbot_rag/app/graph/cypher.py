# --- One-time schema (matches your notebook) ---
SCHEMA = """
CREATE CONSTRAINT patient_id IF NOT EXISTS
FOR (p:Patient) REQUIRE p.patientID IS UNIQUE;

CREATE INDEX section_patient IF NOT EXISTS
FOR (sec:SectionTable) ON (sec.name, sec.patientID);

CREATE INDEX schema_key IF NOT EXISTS
FOR (s:Schema) ON (s.section, s.field, s.patientID);

CREATE INDEX value_key IF NOT EXISTS
FOR (v:Value) ON (v.value, v.valueType, v.patientID);

CREATE CONSTRAINT schema_uuid IF NOT EXISTS
FOR (s:Schema) REQUIRE s.node_id IS UNIQUE;

CREATE CONSTRAINT value_uuid IF NOT EXISTS
FOR (v:Value) REQUIRE v.node_id IS UNIQUE;
"""
# one-time backfill (run via ensure_schema)
BACKFILL_UUIDS = """
MATCH (s:Schema) WHERE s.node_id IS NULL SET s.node_id = randomUUID();
MATCH (v:Value)  WHERE v.node_id IS NULL SET v.node_id = randomUUID();
"""


# --- INGEST_* blocks: lift from your file without changes ---
# Patient node ingestion
INGEST_PATIENT = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
RETURN DISTINCT p
"""
# General Information ingestion
INGEST_GENERAL = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})

// -------- General Information -------
MERGE (gi:SectionTable {name:'GeneralInformation', patientID:r.patient_id})
MERGE (p)-[:HAS_GENERAL_INFORMATION]->(gi)

WITH p, r, gi
UNWIND [
  ['Name',  r.General_Information.name,  'string'],
  ['Title', r.General_Information.title, 'string']
] AS row
WITH p, r, gi, row
WHERE row[1] IS NOT NULL AND row[1] <> ''

WITH p, r, gi, row,
     row[0] AS field,
     row[1] AS raw,
     row[2] AS value_type

WITH p, r, gi, field, value_type,
     CASE value_type
       WHEN 'int'  THEN toInteger(raw)
       WHEN 'date' THEN date(raw)
       ELSE raw
     END AS value
MERGE (s:Schema {section:'GeneralInformation', field:field, patientID:r.patient_id})
MERGE (v:Value  {value:value, valueType:value_type, patientID:r.patient_id})
  ON CREATE SET v.TimeInput = datetime()
MERGE (gi)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Menstrual History ingestion
INGEST_MENSTRUAL = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (menh:SectionTable {name:'MenstrualHistory', patientID:r.patient_id})
MERGE (p)-[:HAS_MENSTRUAL_HISTORY]->(menh)

// scalars
WITH p, r, menh
UNWIND [
  ['AgeOfMenarche',          r.Menstrual_History.`age of menarche`,          'int',     'y'],
  ['LastMenstruationPeriod', r.Menstrual_History.`last menstruation period`, 'date',    null],
  ['Regularity',             r.Menstrual_History.regularity,                 'string',  null],
  ['Flow',                   r.Menstrual_History.flow,                       'string',  null],
  ['Dysmenorrhea',           r.Menstrual_History.dys,                        'string',  null],
  ['IntermenstrualBleeding', r.Menstrual_History.`intermenstrual bleeding`,  'string',  null],
  ['Consanguinity',          r.Menstrual_History.consanguinity,              'boolean', null],
  ['BowelChanges',           r.Menstrual_History.`bowel changes`,            'string',  null],
  ['MenstruationCycleDays',  r.Menstrual_History.`menstruation cycle days`,  'int',     'd'],
  ['MenstruationLength',     r.Menstrual_History.`menstruation length`,      'int',     'd'],
  ['Amenorrhea',             r.Menstrual_History.amenorrhea,                 'string',  null],
  ['AmenorrheaType',         r.Menstrual_History.`amenorrhea type`,          'string',  null],
  ['MedicineUsed',           r.Menstrual_History.`medicine used`,            'boolean', null],
  ['Comments',               r.Menstrual_History.comments,                   'string',  null]
] AS row
WITH p, r, menh, row[0] AS field, row[2] AS value_type, row[3] AS unit, row[1] AS raw
WITH p, r, menh, field, value_type, unit,
     CASE value_type
       WHEN 'int'  THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE toInteger(raw) END
       WHEN 'date' THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE date(raw)     END
       WHEN 'boolean' THEN
         CASE
           WHEN raw IS NULL OR raw='' THEN NULL
           WHEN raw IN [true,false] THEN raw
           WHEN toLower(trim(toString(raw))) IN ['true','yes','y','1']  THEN true
           WHEN toLower(trim(toString(raw))) IN ['false','no','n','0'] THEN false
           ELSE NULL
         END
       ELSE raw
     END AS value
WHERE value IS NOT NULL
MERGE (s:Schema {section:'MenstrualHistory', field:field, patientID:r.patient_id})
MERGE (v:Value  {value:value, valueType:value_type, patientID:r.patient_id})
  ON CREATE SET v.TimeInput = datetime()
SET v.unit = unit
MERGE (menh)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)

// medicine list (normalize to list first)
WITH p, r, menh,
     CASE
       WHEN r.Menstrual_History.medicine IS NULL OR r.Menstrual_History.medicine = '' THEN []
       ELSE r.Menstrual_History.medicine
     END AS meds
UNWIND meds AS med
WITH p, r, menh, med WHERE med IS NOT NULL AND trim(toString(med)) <> ''
MERGE (s:Schema {section:'MenstrualHistory', field:'Medicine', patientID:r.patient_id})
MERGE (v:Value  {value:med, valueType:'string', patientID:r.patient_id})
  ON CREATE SET v.date_observed = date()
MERGE (menh)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Medical History ingestion
INGEST_MEDICAL = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (medh:SectionTable {name:'MedicalHistory', patientID:r.patient_id})
MERGE (p)-[:HAS_MEDICAL_HISTORY]->(medh)

MERGE (s:Schema {section:'MedicalHistory', field:'PastDisease', patientID:r.patient_id})
MERGE (medh)-[:HAS_INFORMATION_OF]->(s)

// normalize map
WITH p, r, medh, s,
     CASE
       WHEN r.Medical_History.`past disease` IS NULL OR r.Medical_History.`past disease` = '' THEN {}
       ELSE r.Medical_History.`past disease`
     END AS pd_map

UNWIND keys(pd_map) AS disease_id
WITH p, r, s, disease_id, pd_map[disease_id] AS dis
WHERE dis IS NOT NULL AND dis <> ''

MERGE (v:Value {valueType:'dict', value:disease_id, patientID:r.patient_id})
SET v.category   = dis.`disease category`,
    v.type       = dis.`disease type`,
    v.since_year = CASE
                     WHEN dis.`disease since when` IS NULL OR dis.`disease since when`='' THEN NULL
                     ELSE toInteger(dis.`disease since when`)
                   END,
    v.on_medication = CASE
        WHEN coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin) IS NULL
             OR coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin) = '' THEN NULL
        WHEN coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin) IN [true,false]
             THEN coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin)
        WHEN toLower(trim(toString(coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin))))
             IN ['true','yes','y','1']  THEN true
        WHEN toLower(trim(toString(coalesce(dis.`disease on medication`, dis.on_medication, dis.on_medicatoin))))
             IN ['false','no','n','0'] THEN false
        ELSE NULL
    END,
    v.comments   = dis.comments
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Obstetrics History ingestion
INGEST_OBSTETRICS = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (obsh:SectionTable {name:'ObstetricsHistory', patientID:r.patient_id})
MERGE (p)-[:HAS_OBSTETRICS_HISTORY]->(obsh)

WITH p, r, obsh
UNWIND [
  ['Gravida',                    r.Obstetrics_History.gravida,                       'int',     'd'],
  ['GestationWeeks',             r.Obstetrics_History.`gestation weeks`,             'int',     'w'],
  ['Outcome',                    r.Obstetrics_History.outcome,                       'string',  null],
  ['SexAssignedBirth',           r.Obstetrics_History.sex_assigned_birth,            'string',  null],
  ['DeliveryMethod',             r.Obstetrics_History.delivery_method,               'string',  null],
  ['TypeOfConceived',            r.Obstetrics_History.`type of conceived`,           'string',  null],
  ['Complication',               r.Obstetrics_History.complication,                  'boolean', null],
  ['CongenitalAnomalies',        r.Obstetrics_History.`congenial anomalies`,         'boolean', null],
  ['HistoryRecurrentAbortion',   r.Obstetrics_History.`history recurrent abortion`,  'boolean', null],
  ['KaryotypingValuation',       r.Obstetrics_History.`karyotyping valuation`,       'boolean', null],
  ['Indication',                 r.Obstetrics_History.indication,                    'string',  null],
  ['SampleType',                 r.Obstetrics_History.`sample type`,                 'string',  null],
  ['KaryotypingResult',          r.Obstetrics_History.`karyotyping result`,          'string',  null],
  ['Comments',                   r.Obstetrics_History.comments,                      'string',  null]
] AS row
WITH p, r, obsh, row[0] AS field, row[2] AS value_type, row[3] AS unit, row[1] AS raw
WITH r, obsh, field, value_type, unit,
     CASE value_type
       WHEN 'int'  THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE toInteger(raw) END
       WHEN 'date' THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE date(raw)     END
       WHEN 'boolean' THEN
         CASE
           WHEN raw IS NULL OR raw='' THEN NULL
           WHEN raw IN [true,false] THEN raw
           WHEN toLower(trim(toString(raw))) IN ['true','yes','y','1']  THEN true
           WHEN toLower(trim(toString(raw))) IN ['false','no','n','0'] THEN false
           ELSE NULL
         END
       ELSE raw
     END AS value
WHERE value IS NOT NULL
MERGE (s:Schema {section:'ObstetricsHistory', field:field, patientID:r.patient_id})
MERGE (v:Value  {value:value, valueType:value_type, patientID:r.patient_id})
  ON CREATE SET v.TimeInput = datetime()
SET v.unit = unit
MERGE (obsh)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Past Medication ingestion
INGEST_PAST_MEDS = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (pm:SectionTable {name:'PastMedication', patientID:r.patient_id})
MERGE (p)-[:HAS_PAST_MEDICATION]->(pm)

MERGE (s:Schema {section:'PastMedication', field:'PastMedication', patientID:r.patient_id})
MERGE (pm)-[:HAS_INFORMATION_OF]->(s)

// normalize to map and drop non-entry keys if any
WITH r, s,
     CASE
       WHEN r.Past_Medication.`past medication` IS NULL OR r.Past_Medication.`past medication` = '' THEN {}
       ELSE r.Past_Medication.`past medication`
     END AS pm_map

UNWIND keys(pm_map) AS med_id
WITH r, s, med_id, pm_map[med_id] AS medi
WHERE medi IS NOT NULL AND medi <> ''

MERGE (v:Value {valueType:'dict', value:med_id, patientID:r.patient_id})
SET v.generic_name = medi.`generic name`,
    v.brand_name   = CASE WHEN medi.`brand name` IS NULL OR medi.`brand name`='' THEN NULL ELSE medi.`brand name` END,
    v.dose         = CASE WHEN medi.does IS NULL OR medi.does='' THEN NULL ELSE medi.does END,
    v.frequency    = CASE WHEN medi.frequency IS NULL OR medi.frequency='' THEN NULL ELSE medi.frequency END,
    v.route        = CASE WHEN medi.route IS NULL OR medi.route='' THEN NULL ELSE medi.route END,
    v.start_date   = CASE WHEN medi.`start date` IS NULL OR medi.`start date`='' THEN NULL ELSE date(medi.`start date`) END,
    v.end_date     = CASE WHEN medi.`end date`   IS NULL OR medi.`end date`  ='' THEN NULL ELSE date(medi.`end date`)   END
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Past Testing ingestion
INGEST_PAST_TESTS = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (pt:SectionTable {name:'PastTesting', patientID:r.patient_id})
MERGE (p)-[:HAS_PAST_TESTING]->(pt)

MERGE (s:Schema {section:'PastTesting', field:'PastTesting', patientID:r.patient_id})
MERGE (pt)-[:HAS_INFORMATION_OF]->(s)

WITH r, s,
     CASE
       WHEN r.Past_Testing.`past testing` IS NULL OR r.Past_Testing.`past testing` = '' THEN {}
       ELSE r.Past_Testing.`past testing`
     END AS pt_map

UNWIND keys(pt_map) AS test_id
WITH r, s, test_id, pt_map[test_id] AS test
WHERE test IS NOT NULL AND test <> ''

MERGE (v:Value {valueType:'dict', value:test_id, patientID:r.patient_id})
SET v.test_name    = test.test_name,
    v.result       = test.result,
    v.date         = CASE WHEN test.date IS NULL OR test.date='' THEN NULL ELSE date(test.date) END,
    v.remark       = CASE WHEN test.`remark/indication` IS NULL OR test.`remark/indication`='' THEN NULL ELSE test.`remark/indication` END,
    v.patient_name = test.patient_name
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Sexual History ingestion
INGEST_SEXUAL = """
WITH $record AS r
MERGE (p:Patient {patientID: r.patient_id})
MERGE (sexh:SectionTable {name:'SexualHistory', patientID:r.patient_id})
MERGE (p)-[:HAS_SEXUAL_HISTORY]->(sexh)

// scalars (exclude STD list)
WITH p, r, sexh
UNWIND [
  ['LastSexRelationDuration', r.Sexual_History.`last sexual relationship duration`, 'string',  null],
  ['LastSexRelationSince',    r.Sexual_History.`last sexual relationship since`,    'string',  null],
  ['Married',                 r.Sexual_History.married,                             'string',  null],
  ['Contraception',           r.Sexual_History.contraception,                       'boolean', null],
  ['ContraceptionMethod',     r.Sexual_History.contraception_method,                'string',  null],
  ['FemaleInfertility',       r.Sexual_History.`female infertility`,                'boolean', null],
  ['IntercourseFrequency',    r.Sexual_History.`intercourse frequency`,             'string',  null],
  ['SexualDysfunction',       r.Sexual_History.`sexual dysfunction`,                'boolean', null],
  ['Dyspareunia',             r.Sexual_History.dyspareunia,                         'boolean', null],
  ['LubricantUse',            r.Sexual_History.`lubricant use`,                     'boolean', null],
  ['OvulationKits',           r.Sexual_History.`ovulation kits`,                    'boolean', null],
  ['SexTransmitDiseaseSince', coalesce(r.Sexual_History.`sexually transmitted disease since`,
                                       r.Sexual_History.`sexual transmitted disease since`),
                               'string',  null],
  ['Comments',                r.Sexual_History.comments,                            'string',  null]
] AS row
WITH r, sexh, row[0] AS field, row[2] AS value_type, row[3] AS unit, row[1] AS raw
WITH r, sexh, field, value_type, unit,
     CASE value_type
       WHEN 'int'  THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE toInteger(raw) END
       WHEN 'date' THEN CASE WHEN raw IS NULL OR raw='' THEN NULL ELSE date(raw)     END
       WHEN 'boolean' THEN
         CASE
           WHEN raw IS NULL OR raw='' THEN NULL
           WHEN raw IN [true,false] THEN raw
           WHEN toLower(trim(toString(raw))) IN ['true','yes','y','1']  THEN true
           WHEN toLower(trim(toString(raw))) IN ['false','no','n','0'] THEN false
           ELSE NULL
         END
       ELSE raw
     END AS value
WHERE value IS NOT NULL
MERGE (s:Schema {section:'SexualHistory', field:field, patientID:r.patient_id})
MERGE (v:Value  {value:value, valueType:value_type, patientID:r.patient_id})
  ON CREATE SET v.TimeInput = datetime()
SET v.unit = unit
MERGE (sexh)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)

// STD list
WITH r, sexh,
     CASE
       WHEN r.Sexual_History.`sexually transmitted disease (STD)` IS NULL
            OR r.Sexual_History.`sexually transmitted disease (STD)` = '' THEN []
       ELSE r.Sexual_History.`sexually transmitted disease (STD)`
     END AS std_list
UNWIND std_list AS std
WITH r, sexh, std WHERE std IS NOT NULL AND trim(toString(std)) <> ''
MERGE (s:Schema {section:'SexualHistory', field:'STD', patientID:r.patient_id})
MERGE (v:Value  {value:std, valueType:'string', patientID:r.patient_id})
MERGE (sexh)-[:HAS_INFORMATION_OF]->(s)
MERGE (s)-[:HAS_VALUE]->(v)
"""
# Combine all the ingestion queries
SECTION_QUERIES = [
    INGEST_PATIENT,
    INGEST_GENERAL,
    INGEST_MENSTRUAL,
    INGEST_MEDICAL,
    INGEST_OBSTETRICS,
    INGEST_PAST_MEDS,
    INGEST_PAST_TESTS,
    INGEST_SEXUAL,
]


# Retrieval Cypher for a patient subgraph (unchanged)
RETRIEVE_PATIENT_CYPHER = """
MATCH (p:Patient {patientID:$pid})
MATCH (p)-[r1]->(sec:SectionTable {patientID:$pid})
WHERE type(r1) IN [
  'HAS_GENERAL_INFORMATION','HAS_MENSTRUAL_HISTORY','HAS_MEDICAL_HISTORY',
  'HAS_OBSTETRICS_HISTORY','HAS_PAST_MEDICATION','HAS_PAST_TESTING','HAS_SEXUAL_HISTORY'
]
OPTIONAL MATCH (sec)-[r2:HAS_INFORMATION_OF]->(sch:Schema {patientID:$pid})
OPTIONAL MATCH (sch)-[r3:HAS_VALUE]->(val:Value {patientID:$pid})
WITH collect(DISTINCT p) AS P,
     collect(DISTINCT sec) AS SECS,
     collect(DISTINCT sch) AS SCHEMAS,
     [v IN collect(DISTINCT val) WHERE v IS NOT NULL] AS VALS,
     collect(DISTINCT r1) + collect(DISTINCT r2) + collect(DISTINCT r3) AS RELS
RETURN P + SECS + SCHEMAS + VALS AS nodes, RELS AS rels
"""

