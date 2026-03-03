# Code Citations

## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/jonromero/jonio_website/blob/492cd6da9bb1bfaa8de0b9c42609827773c90376/content/pages/hugcoin.md

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: unknown
https://github.com/crossbario/crossbar/blob/0089c1ef6fbbb87fc7316088a91f1859fa84eeb0/test/test_xbr_marketmaker/work/test3.py

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: MIT
https://github.com/MyEtherWallet/etherwallet/blob/9623a34d7bcd9892140d3d8f02745eade14e7415/chrome-extension/js/etherwallet-master.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: MIT
https://github.com/blockscout/blockscout-rs/blob/3f326e1e19cbff67053fd0c2ec3e071d3bb6d4b4/smart-contract-verifier/smart-contract-verifier/src/vyper/artifacts.rs

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decim
```


## License: unknown
https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/015d0105102504dc8733a18c3543f87f1829a5e8/contracts/goerli/f0/F0BFD0298866EBcA9B55a170A67BC863DbC2679E_CryptoPunksMarket.sol

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "
```


## License: GPL-3.0
https://github.com/xrchz/rocketsplit/blob/b89a38eb5425dbc97bc4e2e34204246a10ba7f4c/react-ui/src/components/WithdrawalDisplay.js

```
# WASI x402 Payment Verification Middleware - x402.py

````python
# filepath: wasi-backend-api/src/middleware/x402_payment_verification.py
"""
x402 Payment Verification Middleware
West African Shipping & Economic Intelligence Platform
Handles USDC payments on Base chain with real-time verification
Integrates with Stripe, Flutterwave, and on-chain verification
"""

import os
import json
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from functools import wraps

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SECTION 1: IMPORTS & CONFIGURATION
# ============================================================================

# Web3 & Blockchain
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_defunct

# Database
from database.models import (
    User, X402Transaction, X402Tier, QueryLog
)
from database.connection import get_session

# External APIs
import stripe
import requests

# Environment variables
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453
USDC_CONTRACT_ADDRESS = os.getenv('USDC_BASE_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913')
WASI_WALLET_ADDRESS = os.getenv('WASI_WALLET_ADDRESS', '0x...')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Payment gateways
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
FLUTTERWAVE_API_KEY = os.getenv('FLUTTERWAVE_API_KEY')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH')

stripe.api_key = STRIPE_API_KEY

# USDC ABI (ERC20 standard)
USDC_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable"
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "
```

