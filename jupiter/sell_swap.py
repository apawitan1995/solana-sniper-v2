import base64, json, requests, time, os, sys

from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned
from solders.signature import Signature

from solana.rpc.api import RPCException

from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts

from utils.webhook import sendWebhook
from utils.birdeye import getSymbol
from utils.constants import LAMPORTS_PER_SOL


def sell(ctx, payer, TOKEN_TO_SWAP_SELL, config):
    token_symbol, _ = getSymbol(TOKEN_TO_SWAP_SELL)

    slippageBps = int(config.get("INVESTMENT", "slippage"))
    computeUnitPriceMicroLamports = int(config.get("INVESTMENT", "computeUnitPriceMicroLamports"))


    txnBool = True
    while txnBool:
        Attempt = True
        while Attempt:
            balanceBool = True
            while balanceBool:
                tokenPk = Pubkey.from_string(TOKEN_TO_SWAP_SELL)

                accountProgramId = ctx.get_account_info_json_parsed(tokenPk)
                programid_of_token = accountProgramId.value.owner

                accounts = ctx.get_token_accounts_by_owner_json_parsed(payer.pubkey(),TokenAccountOpts(program_id=programid_of_token)).value
                for account in accounts:
                    mint = account.account.data.parsed['info']['mint']
                    if mint == TOKEN_TO_SWAP_SELL:
                        tokenBalanceLamports = int(account.account.data.parsed['info']['tokenAmount']['amount'])
                        break
                if int(tokenBalanceLamports) > 0:
                    balanceBool = False
                else:
                    print("No Balance, Retrying...")
                    time.sleep(5)
# ========================================================================================================
            # Swap Info
            print("Token Balance [Lamports]: ",tokenBalanceLamports)
            print("3. Get Route for swap...")

            quote_response = requests.get('https://quote-api.jup.ag/v6/quote', params={
                'inputMint': TOKEN_TO_SWAP_SELL,
                'outputMint': 'So11111111111111111111111111111111111111112',
                'amount': tokenBalanceLamports,
                'slippageBps': slippageBps
            }).json()
# ========================================================================================================
            print("4. Get the serialized transactions to perform the swap...")
            # Get the serialized transactions to perform the swap
            url = "https://quote-api.jup.ag/v6/swap"
            payload = json.dumps({
            "userPublicKey": str(payer.pubkey()),
            "wrapAndUnwrapSol": True,
            'computeUnitPriceMicroLamports': computeUnitPriceMicroLamports,
            "quoteResponse": quote_response
            })
            headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
            }
            response = requests.request("POST", url, headers=headers, data=payload)
            # print(response.text)
            if (response.status_code == 200):
                instructions_all = (response).json()
                # print(swap_instructions)
                Attempt = False
            else:
                print("Retying...")
        swap_instruction = instructions_all["swapTransaction"]
        raw_tx = VersionedTransaction.from_bytes(base64.b64decode(swap_instruction))
        
# ========================================================================================================
        print("5. Sign Transaction...")
        signature = payer.sign_message(to_bytes_versioned(raw_tx.message))
        signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])
# ========================================================================================================
        try:
            print("6. Execute Transaction...")
            start_time = time.time()
            txid = (ctx.send_transaction(
                signed_tx
            # opts=TxOpts(skip_confirmation=False, skip_preflight=True, max_retries=2),

            ))

            print(f"Transaction ID: {txid.value}")
            print(f"Transaction URL: https://solscan.io/tx/{txid.value}")

            txid_string_sig = Signature.from_string(str(txid.value))
            checkTxn = True
            while checkTxn:
                try:
                    status = ctx.get_transaction(txid_string_sig,"jsonParsed", max_supported_transaction_version=0)
                    FeesUsed = (status.value.transaction.meta.fee) / LAMPORTS_PER_SOL
                    if status.value.transaction.meta.err == None:
                        print("Transaction Success")
                        print("Transaction Fees: {:.10f} SOL".format(FeesUsed))

                        end_time = time.time()
                        execution_time = end_time - start_time
                        print(f"Execution time: {execution_time} seconds")

                        txnBool = False
                        checkTxn = False

                        return txid_string_sig

                    else:
                        print("Transaction Failed: ", status.value.transaction.meta.err)
                        end_time = time.time()
                        execution_time = end_time - start_time
                        print(f"Execution time: {execution_time} seconds")
                        checkTxn = False
                except Exception as e:
                    sendWebhook(f"e|Sell ERROR {token_symbol}",f"{e}")
                    print("Retrying...")

            
                
        except RPCException as e:
            print(f"Error: [{e.args[0].message}]...\nRetrying...")
            sendWebhook(f"e|SELL ERROR {token_symbol}",f"{e.args[0].data.logs}")
            # txnBool = False
            # return "failed"
        except Exception as e:
            print(f"Error: [{e}]...\nEnd...")
            txnBool = False
            return "failed"
