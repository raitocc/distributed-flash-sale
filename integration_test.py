import os
import sys
import subprocess
import time
import httpx
import uuid
import asyncio
from pathlib import Path

# 定义各服务的测试端口和地址
BASE_URLS = {
    "user": "http://127.0.0.1:9001",
    "product": "http://127.0.0.1:9002",
    "order": "http://127.0.0.1:9003",
    "inventory": "http://127.0.0.1:9004"
}

# 临时数据库路径
DB_FILES = {
    "user": "test_user.db",
    "product": "test_product.db",
    "order": "test_order.db",
    "inventory": "test_inventory.db"
}

def clean_dbs():
    print("清空遗留的测试数据库文件...")
    for db in DB_FILES.values():
        if os.path.exists(db):
            try:
                os.remove(db)
            except BaseException as e:
                print(f"清空 {db} 失败: {e}")

def get_python_executable(service_dir: str):
    """尝试获取对应服务的虚拟环境 Python 解释器，若无则使用系统默认的"""
    venv_python = Path(os.getcwd()) / service_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

async def wait_for_services(timeout=15):
    """等待所有服务启动成功 (探测自带的 /docs 或 /openapi.json 返回)"""
    start_time = time.time()
    async with httpx.AsyncClient() as client:
        for name, url in BASE_URLS.items():
            ready = False
            while time.time() - start_time < timeout:
                try:
                    res = await client.get(f"{url}/openapi.json")
                    if res.status_code == 200:
                        ready = True
                        print(f"[{name}] 服务启动正常")
                        break
                except httpx.RequestError:
                    pass
                await asyncio.sleep(0.5)
            if not ready:
                raise Exception(f"服务 {name} 在 {url} 启动超时！请检查。")

async def run_integration_tests():
    # 1. 启动微服务进程
    processes = []
    services = [
        ("user_service", 9001, {"DATABASE_URL": f"sqlite:///../{DB_FILES['user']}", "SECRET_KEY": "testsecret"}),
        ("product_service", 9002, {"DATABASE_URL": f"sqlite:///../{DB_FILES['product']}", "SECRET_KEY": "testsecret"}),
        ("order_service", 9003, {"DATABASE_URL": f"sqlite:///../{DB_FILES['order']}", "SECRET_KEY": "testsecret", "PRODUCT_SERVICE_URL": BASE_URLS["product"], "INVENTORY_SERVICE_URL": BASE_URLS["inventory"]}),
        ("inventory_service", 9004, {"DATABASE_URL": f"sqlite:///../{DB_FILES['inventory']}", "SECRET_KEY": "testsecret"}),
    ]

    print("================ 启动隔离测试环境 ================")
    clean_dbs()
    
    for folder, port, env_vars in services:
        env = os.environ.copy()
        env.update(env_vars)
        python_exe = get_python_executable(folder)
        
        # 启动 uvicorn
        cmd = [python_exe, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)]
        current_dir = os.path.join(os.getcwd(), folder)
        print(f"正在启动 {folder} -> {cmd}")
        
        # 不使用 stdout=subprocess.PIPE，以免死锁。输出导向黑洞保持控制台干净，或者直接放着。
        log_file = open(f"test_run_{folder}.log", "w", encoding="utf-8")
        p = subprocess.Popen(cmd, cwd=current_dir, env=env, stdout=log_file, stderr=log_file)
        processes.append((p, log_file))

    try:
        # 等待服务初始化完成
        await wait_for_services()
        print("所有服务均已 Ready。开始执行全链路 E2E 验证...")

        async with httpx.AsyncClient() as client:
            username = f"testuser_{uuid.uuid4().hex[:6]}"
            password = "testpassword123"

            # ==========================================
            # 1. 用户注册与登录
            # ==========================================
            print(">> 正在测试: [用户注册]")
            res = await client.post(f"{BASE_URLS['user']}/api/users/register", json={"username": username, "password": password})
            assert res.status_code == 200, f"受挫: {res.text}"
            res_json = res.json()
            assert res_json["code"] == 200
            print("   成功.")

            print(">> 正在测试: [用户登录]")
            res = await client.post(f"{BASE_URLS['user']}/api/users/login", json={"username": username, "password": password})
            assert res.status_code == 200
            res_json = res.json()
            assert res_json["code"] == 200
            token = res_json["data"]["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("   成功获取 Token.")

            # ==========================================
            # 2. 创建测试商品
            # ==========================================
            print(">> 正在测试: [录入新商品]")
            res = await client.post(
                f"{BASE_URLS['product']}/api/products", 
                json={"name": "Test iPhone Plus", "description": "Good", "original_price": 1999.0, "flash_price": 999.0},
                headers=headers
            )
            assert res.status_code == 200, f"创建商品失败，状态码: {res.status_code}, 返回: {res.text}"
            product_id = res.json()["data"]["id"]
            print(f"   商品录入成功 (ID: {product_id}).")

            # ==========================================
            # 3. 设置初始库存 (仅 1 件)
            # ==========================================
            print(">> 正在测试: [设定商品秒杀库存 1]")
            res = await client.post(
                f"{BASE_URLS['inventory']}/api/inventory",
                json={"product_id": product_id, "total_stock": 1}
            )
            assert res.status_code == 200
            print("   库存到位.")

            # ==========================================
            # 4. 创建有效订单 (查价 -> 锁库存)
            # ==========================================
            print(">> 正在测试: [首次合法下单 (期望成功)]")
            res = await client.post(
                f"{BASE_URLS['order']}/api/orders",
                json={"product_id": product_id},
                headers=headers
            )
            assert res.status_code == 200, f"下单报错: {res.text}"
            order_data = res.json()["data"]
            order_id = order_data["id"]
            assert order_data["status"] == "PENDING"
            print("   成功! 防超卖体系与分布式跨微服务通信畅通。")

            # ==========================================
            # 5. 防超卖阻断测试 (库存已锁，期望失败)
            # ==========================================
            print(">> 正在测试: [库存不足时的二次抢购 (期望被400阻断)]")
            res2 = await client.post(
                f"{BASE_URLS['order']}/api/orders",
                json={"product_id": product_id},
                headers=headers
            )
            # 根据重构规范，库存拦截会原样顶上来，状态码应该是 HTTP 400
            assert res2.status_code == 400
            assert res2.json()["code"] == 400
            print(f"   如预期被拦截，核心报错: {res2.json()['message']}")

            # ==========================================
            # 6. 付款全量测试
            # ==========================================
            print(">> 正在测试: [订单确认与真实扣减库存]")
            res_pay = await client.post(
                f"{BASE_URLS['order']}/api/orders/{order_id}/pay",
                headers=headers
            )
            assert res_pay.status_code == 200
            assert res_pay.json()["data"]["status"] == "PAID"
            print("   付款并扣库存流程完全成功！")
            print("================ 所有测试完美闭环 ================")
            
    finally:
        # 清理进程
        print("正在关闭所有驻留的子微服务进程...")
        for p, log_file in processes:
            p.terminate()
            p.wait()
            log_file.close()
        
        # 删除临时数据库
        clean_dbs()
        print("独立隔离测试现场已销毁。")

if __name__ == "__main__":
    asyncio.run(run_integration_tests())
