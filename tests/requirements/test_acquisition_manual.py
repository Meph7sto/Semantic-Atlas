
import requests
import json
import json

def test_extraction():
    url = "http://localhost:8000/acquisition/extract"
    text = """
    好的，那个，我们能不能做一个这样的东西，就是财务那边希望看能不能自动对账。
    因为现在如果是人工的话，太慢了，而且容易出错。
    我想大概需要能在系统里导入银行流水，然后跟我们自己的单据匹配。
    如果匹配不上的，要能高亮显示出来。
    另外，老板也说了，这个东西必须在下个月底上线，不然会影响审计。
    性能方面嘛，至少支持一万条数据一分钟内搞定吧。
    """
    
    payload = {
        "text": text,
        "chunk_size": 1000,
        "overlap": 100
    }
    
    print(f"Sending request to {url}...")
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print("Response received:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # Simple assertions
        assert "business_requirements" in data
        assert "stakeholder_requirements" in data
        assert "system_requirements" in data
        
        print("\nSUCCESS: Extraction structure verified.")
        
    except Exception as e:
        print(f"FAILED: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response content: {e.response.text}")

if __name__ == "__main__":
    test_extraction()
