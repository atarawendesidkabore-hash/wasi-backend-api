"""
eCFA CBDC COBOL Record Formatters.

Generates fixed-width records compatible with legacy BCEAO and
commercial bank COBOL systems (STAR-UEMOA, core banking).

Record layouts follow PIC notation:
  PIC 9(N)   = N-digit numeric
  PIC 9(N)V9(M) = N.M decimal numeric
  PIC X(N)   = N-character alphanumeric

Settlement record: 200 chars fixed width
Transaction record: 150 chars fixed width
"""
from datetime import timezone, datetime


def format_settlement_cobol(settlement: dict) -> str:
    """Format a settlement record as a 200-char COBOL fixed-width line.

    Layout:
      01-10  SETTLEMENT_ID    PIC X(10)    Settlement reference
      11-20  SETTLE_TYPE      PIC X(10)    DOMESTIC_NET / CROSS_BORDER_NET
      21-30  BANK_A_CODE      PIC X(10)    Payer bank BIC/code
      31-40  BANK_B_CODE      PIC X(10)    Payee bank BIC/code
      41-55  GROSS_AMT        PIC 9(13)V99 Gross amount (cents)
      56-70  NET_AMT          PIC 9(13)V99 Net amount (cents)
      71-80  DIRECTION        PIC X(10)    A_TO_B / B_TO_A / BALANCED
      81-87  TXN_COUNT        PIC 9(7)     Number of transactions
      88-97  COUNTRY_CODES    PIC X(10)    Participating countries
      98-105 WINDOW_START     PIC 9(8)     YYYYMMDD
     106-113 WINDOW_END       PIC 9(8)     YYYYMMDD
     114-123 STATUS           PIC X(10)    pending / confirmed
     124-143 STAR_UEMOA_REF   PIC X(20)    RTGS reference
     144-151 SETTLE_DATE      PIC 9(8)     YYYYMMDD
     152-200 FILLER           PIC X(49)    Reserved
    """
    sid = str(settlement.get("settlement_id", ""))[:10].ljust(10)
    stype = str(settlement.get("settlement_type", ""))[:10].ljust(10)
    bank_a = str(settlement.get("bank_a_code", ""))[:10].ljust(10)
    bank_b = str(settlement.get("bank_b_code", ""))[:10].ljust(10)

    gross = int(settlement.get("gross_amount_ecfa", 0) * 100)
    net = int(settlement.get("net_amount_ecfa", 0) * 100)
    gross_s = f"{gross:015d}"
    net_s = f"{net:015d}"

    direction = str(settlement.get("direction", ""))[:10].ljust(10)
    txn_count = f"{settlement.get('transaction_count', 0):07d}"
    countries = str(settlement.get("country_codes", ""))[:10].ljust(10)

    ws = settlement.get("window_start", datetime.now(timezone.utc))
    we = settlement.get("window_end", datetime.now(timezone.utc))
    ws_s = ws.strftime("%Y%m%d") if isinstance(ws, datetime) else str(ws)[:8].ljust(8)
    we_s = we.strftime("%Y%m%d") if isinstance(we, datetime) else str(we)[:8].ljust(8)

    status = str(settlement.get("status", ""))[:10].ljust(10)
    star_ref = str(settlement.get("star_uemoa_ref", ""))[:20].ljust(20)

    settle_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    filler = " " * 49

    record = (
        f"{sid}{stype}{bank_a}{bank_b}"
        f"{gross_s}{net_s}{direction}{txn_count}"
        f"{countries}{ws_s}{we_s}{status}{star_ref}"
        f"{settle_date}{filler}"
    )
    return record[:200].ljust(200)


def format_transaction_cobol(tx: dict) -> str:
    """Format a transaction as a 150-char COBOL fixed-width line.

    Layout:
      01-10  TX_ID            PIC X(10)    Transaction reference
      11-20  TX_TYPE          PIC X(10)    TRANSFER_P2P / MERCHANT_PAYMENT / etc
      21-35  AMOUNT           PIC 9(13)V99 Amount in centimes
      36-50  FEE              PIC 9(13)V99 Fee in centimes
      51-60  SENDER_CC        PIC X(10)    Sender country
      61-70  RECEIVER_CC      PIC X(10)    Receiver country
      71-78  TX_DATE          PIC 9(8)     YYYYMMDD
      79-84  TX_TIME          PIC 9(6)     HHMMSS
      85-94  STATUS           PIC X(10)    completed / failed
      95-99  KYC_TIER         PIC 9(5)     KYC tier at time
     100-109 AML_STATUS       PIC X(10)    cleared / flagged
     110-144 COBOL_REF        PIC X(35)    SWIFT-compatible reference
     145-150 FILLER           PIC X(6)     Reserved
    """
    tx_id = str(tx.get("transaction_id", ""))[:10].ljust(10)
    tx_type = str(tx.get("tx_type", ""))[:10].ljust(10)

    amount = int(tx.get("amount_ecfa", 0) * 100)
    fee = int(tx.get("fee_ecfa", 0) * 100)
    amount_s = f"{amount:015d}"
    fee_s = f"{fee:015d}"

    sender_cc = str(tx.get("sender_country", ""))[:10].ljust(10)
    receiver_cc = str(tx.get("receiver_country", ""))[:10].ljust(10)

    ts = tx.get("initiated_at", datetime.now(timezone.utc))
    if isinstance(ts, datetime):
        tx_date = ts.strftime("%Y%m%d")
        tx_time = ts.strftime("%H%M%S")
    else:
        tx_date = "00000000"
        tx_time = "000000"

    status = str(tx.get("status", ""))[:10].ljust(10)
    kyc_tier = f"{tx.get('kyc_tier_at_time', 0):05d}"
    aml_status = str(tx.get("aml_status", ""))[:10].ljust(10)
    cobol_ref = str(tx.get("cobol_ref", ""))[:35].ljust(35)
    filler = " " * 6

    record = (
        f"{tx_id}{tx_type}{amount_s}{fee_s}"
        f"{sender_cc}{receiver_cc}{tx_date}{tx_time}"
        f"{status}{kyc_tier}{aml_status}{cobol_ref}{filler}"
    )
    return record[:150].ljust(150)
