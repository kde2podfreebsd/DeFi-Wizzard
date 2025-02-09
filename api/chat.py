from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
import json
import httpx
import os
from atoma.atoma_connector import AtomaAPIClient
import re
from logger.logger import setup_logger

logger = setup_logger('app_logger')

router = APIRouter()
USER_CONTEXT_FILE = "user_contexts.json"

def filter_top_pools_bluefin(pools_data):
    filtered_pools = []
    for pool in pools_data:
        if "day" in pool and "apr" in pool["day"]:
            apr_total = float(pool["day"]["apr"]["total"])
            symbol = pool.get("symbol", "Unknown")
            token_a = pool["tokenA"]["info"].get("symbol", "Unknown")
            token_b = pool["tokenB"]["info"].get("symbol", "Unknown")
            address = pool.get("address", "Unknown")

            filtered_pools.append({
                "address": address,
                "tokenA": token_a,
                "tokenB": token_b,
                "pool_name": symbol,
                "apr": apr_total
            })

    top_pools = sorted(filtered_pools, key=lambda x: x["apr"], reverse=True)[:25]
    print("FILTER POOLS: ", top_pools)
    return top_pools

async def get_bluefin_pools_apr():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://swap.api.sui-prod.bluefin.io/api/v1/pools/info",
            headers={"accept": "application/json"},
        )
        print("GET BLUEFIN POOLS APR:", response.json())
        response.raise_for_status()
        return response.json()

def get_atoma_client() -> AtomaAPIClient:
    return AtomaAPIClient()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

class ClearContextRequest(BaseModel):
    chat_id: str

def remove_think_tags(analysis: str) -> str:
    pattern = r"<think>.*?</think>"
    cleaned_analysis = re.sub(pattern, "", analysis, flags=re.DOTALL)
    return cleaned_analysis.strip()


@router.post("/message")
async def chat_with_ai(request: ChatRequest, wallet_id: str = Query(..., description="ID пользователя"), client: AtomaAPIClient = Depends(get_atoma_client)):
    first_prompt = f"""
    Вы выступаете в роли посредника между пользователем и системой управления блокчейном Sui.
    Ваша задача - определить, можно ли выполнить запрос пользователя с помощью доступных функций.
    Доступные функции:
    1) balance(address) - получение баланса аккаунта по адресу
    2) transfer(recipient, amount) - перевод токенов на другой адрес
    4) bluefin_apr_top_pools() - топ пулов Bluefin для стейкинга
    5) get_user_positions(address) - получение позиций пользователя по адресу
    6) swap(token_in, amount_in, slippage, use_native, fee_tier, min_amount_out) - своп токенов
    7) open(position_params) - открытие новой позиции ликвидности
    8) collect(position_id) - сбор наград и комиссий для позиции
    9) close(position_id) - закрытие позиции ликвидности
    Формат ответа должен быть строго JSON:
    {{\"function\": \"имя_функции\", \"parameters\": {{\"параметр1\": \"значение1\", \"параметр2\": \"значение2\"}}}}
    Если действие невозможно выполнить, верните: {{}}

    Запрос пользователя: {request.message}
    """
    logger.info("First prompt sent to AI:\n%s", first_prompt)

    first_response = await client.create_chat_completion(
        model="deepseek-ai/DeepSeek-R1",
        messages=[{"role": "system", "content": first_prompt}]
    )
    parsed_first_response = first_response["choices"][0]["message"]["content"]
    first_output = remove_think_tags(parsed_first_response)
    logger.debug('First output from AI: %s', first_output)

    if first_output:
        logger.debug("Proceeding with further processing...")
        second_prompt = f"""
        Если в предыдущем ответе было указано имя функции, ваша задача - извлечь необходимые параметры из сообщения пользователя и выполнить соответствующее действие.
        Извлеките параметры в формате JSON:
        {first_output}
        Если функция не указана, просто сформируйте дружелюбный ответ пользователю.
        Сообщение пользователя: {request.message}
        """
        logger.info("Second prompt sent to AI:\n%s", second_prompt)

        second_response = await client.create_chat_completion(
            model="deepseek-ai/DeepSeek-R1",
            messages=[{"role": "system", "content": second_prompt}]
        )
        parsed_second_response = second_response["choices"][0]["message"]["content"]
        parsed_second_response = remove_think_tags(parsed_second_response)
        logger.debug("Second output from AI: %s", parsed_second_response)

        response_to_check = parsed_second_response.replace('```', '').replace('json', '')
        logger.debug("Response to check: %s (%s)", response_to_check, type(response_to_check))

        try:
            action_data = json.loads(response_to_check)
            if 'function' in action_data and 'parameters' in action_data:
                function_name = action_data['function']
                params = action_data['parameters']

                if function_name == 'balance':
                    address = params.get('address')
                    if address:
                        logger.info("Executing balance check for address: %s", address)
                        return ChatResponse(response=f"Баланс проверяется для адреса: {address}")

                elif function_name == 'transfer':
                    recipient = params.get('recipient')
                    amount = params.get('amount')
                    if recipient and amount:
                        logger.info("Transferring %s to %s", amount, recipient)

                        return ChatResponse(response=f"Перевод {amount} на адрес {recipient} выполняется...")

                elif function_name == 'bluefin_apr_top_pools':
                    pools_data = await get_bluefin_pools_apr()
                    top_pools = filter_top_pools_bluefin(pools_data)
                    return ChatResponse(response=f"Топ пулы на BlueFin https://trade.bluefin.io/\n\n {top_pools}")

                elif function_name == 'get_user_positions':
                    address = params.get('address')
                    if address:
                        logger.info("Fetching user positions for address: %s", address)
                        return ChatResponse(response=f"Получение позиций для адреса: {address}")

                elif function_name == 'swap':
                    token_in = params.get('token_in')
                    amount_in = params.get('amount_in')
                    slippage = params.get('slippage')
                    use_native = params.get('use_native')
                    fee_tier = params.get('fee_tier')
                    min_amount_out = params.get('min_amount_out')
                    if all([token_in, amount_in, slippage, use_native, fee_tier, min_amount_out]):
                        logger.info("Executing swap: %s -> %s", token_in, amount_in)
                        return ChatResponse(response=f"Выполняется своп {token_in} в размере {amount_in}")

                elif function_name == 'open':
                    position_params = params.get('position_params')
                    if position_params:
                        logger.info("Opening liquidity position with params: %s", position_params)
                        return ChatResponse(response=f"Открытие позиции ликвидности с параметрами: {position_params}")

                elif function_name == 'collect':
                    position_id = params.get('position_id')
                    if position_id:
                        logger.info("Collecting rewards for position ID: %s", position_id)
                        return ChatResponse(response=f"Сбор наград для позиции: {position_id}")

                elif function_name == 'close':
                    position_id = params.get('position_id')
                    if position_id:
                        logger.info("Closing position ID: %s", position_id)
                        return ChatResponse(response=f"Закрытие позиции: {position_id}")

                else:
                    return ChatResponse(response=parsed_second_response)

        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response: %s", response_to_check)
            return ChatResponse(response=parsed_second_response)

    else:
        logger.warning("AI did not provide a valid function to execute.")
        return ChatResponse(response=first_output)


@router.post("/clear_context", summary="Очистка контекста диалога")
async def clear_context(wallet_id: str = Query(..., description="ID пользователя")):
    return {"response": f"Контекст для чата {wallet_id} очищен"}