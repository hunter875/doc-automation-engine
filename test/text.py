import pdfplumber
import os
import re

def clean_text_for_llm(raw_text):
    if not raw_text:
        return ""
    
    # Tách từng dòng ra
    lines = raw_text.splitlines()
    
    cleaned_lines = []
    for line in lines:
        # Xóa khoảng trắng thừa ở 2 đầu, nhưng giữ nguyên khoảng trắng ở giữa (quan trọng cho layout cột)
        stripped = line.strip()
        if stripped: 
            cleaned_lines.append(stripped)
            
    # Nối lại bằng 1 dấu xuống dòng. 
    # Mỗi dòng lúc này tương đương 1 hàng dữ liệu của bảng hoặc 1 câu văn.
    return "\n".join(cleaned_lines)

def extract_for_ollama(pdf_path, output_txt="context_cho_ollama.txt"):
    if not os.path.exists(pdf_path):
        print(f"[!] Lỗi: Không tìm thấy file '{pdf_path}'")
        return

    print(f"[*] Đang băm file '{pdf_path}' sang chuẩn LLM...")
    print("=" * 60)
    
    full_context = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # KỸ THUẬT QUAN TRỌNG: layout=True ép pdfplumber giữ lại khoảng cách vật lý của text.
            # Cột nào cách xa nhau nó sẽ tự điền Space vào giữa, giúp LLM nhìn thấy cấu trúc bảng qua Text.
            text = page.extract_text(layout=True)
            
            # Fallback nếu layout=True bị lỗi
            if not text:
                text = page.extract_text() 
            
            if text:
                cleaned = clean_text_for_llm(text)
                # Đánh dấu phân trang rõ ràng để LLM không bị lú ngữ cảnh
                full_context.append(f"--- BẮT ĐẦU TRANG {i + 1} ---\n{cleaned}\n--- KẾT THÚC TRANG {i + 1} ---\n")

    # Gom toàn bộ lại
    final_payload = "\n".join(full_context)
    
    # Ghi ra file để copy-paste cho tiện
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(final_payload)
        
    print(f"[+] THÀNH CÔNG! Đã lưu ngữ cảnh siêu sạch vào file: {output_txt}")
    print("\n[*] MẪU PREVIEW (Dữ liệu bảng giờ đã thành hàng ngang):")
    print("-" * 60)
    # In thử một đoạn ở giữa (khoảng trang 4) nơi chứa dữ liệu bảng để mày check
    print(final_payload[1500:2500]) 
    print("-" * 60)

if __name__ == "__main__":
    FILE_CAN_TEST = "KV30 BCN 21.03.26.pdf" 
    extract_for_ollama(FILE_CAN_TEST)