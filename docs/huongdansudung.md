# 📘 Hướng dẫn sử dụng Hệ thống Trích xuất Tài liệu (IDP)

> **Dành cho người dùng không chuyên kỹ thuật**
> Phiên bản: 1.1 · Cập nhật: 13/04/2026

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Đăng nhập & Chọn tổ chức](#2-đăng-nhập--chọn-tổ-chức)
3. [Trang chủ — Dashboard](#3-trang-chủ--dashboard)
4. [Quy trình làm việc từ A đến Z](#4-quy-trình-làm-việc-từ-a-đến-z)
5. [Tab ⚙️ Mẫu — Quản lý mẫu trích xuất](#5-tab-️-mẫu--quản-lý-mẫu-trích-xuất)
6. [Tab 📤 Hồ sơ — Nộp và theo dõi tài liệu](#6-tab--hồ-sơ--nộp-và-theo-dõi-tài-liệu)
7. [Tab 🔍 Duyệt — Kiểm tra và phê duyệt](#7-tab--duyệt--kiểm-tra-và-phê-duyệt)
8. [Tab 📊 Báo cáo — Tổng hợp và xuất](#8-tab--báo-cáo--tổng-hợp-và-xuất)
9. [Kỳ báo cáo — Tổng hợp theo chu kỳ](#9-kỳ-báo-cáo--tổng-hợp-theo-chu-kỳ)
10. [Trang 📄 Tài liệu](#10-trang--tài-liệu)
11. [Các trạng thái hồ sơ](#11-các-trạng-thái-hồ-sơ)
12. [Câu hỏi thường gặp](#12-câu-hỏi-thường-gặp)
13. [Khi nào cần liên hệ IT](#13-khi-nào-cần-liên-hệ-it)

---

## 1. Tổng quan hệ thống

Hệ thống IDP (Intelligent Document Processing — Xử lý tài liệu thông minh) giúp bạn:

| Bạn làm gì | Hệ thống làm gì |
|---|---|
| Tải file PDF lên | AI tự động đọc và rút thông tin quan trọng |
| Kiểm tra kết quả AI | Bạn duyệt / chỉnh sửa nếu cần |
| Chọn các hồ sơ đã duyệt | Hệ thống tổng hợp thành báo cáo |
| Nhấn xuất | Ra file Excel / Word / JSON |

**Luồng cơ bản:**

```
Tải PDF lên  →  AI xử lý  →  Bạn duyệt  →  Tổng hợp  →  Xuất báo cáo
```

**Bạn không cần biết lập trình.** Chỉ cần biết dùng trình duyệt web.

---

## 2. Đăng nhập & Chọn tổ chức

### Đăng nhập

1. Mở trình duyệt (Chrome / Edge), nhập địa chỉ do IT cấp
2. Nhập **Email** và **Mật khẩu**
3. Nhấn **Đăng nhập**

> ⚠️ Nếu quên mật khẩu, liên hệ IT. Hệ thống hiện chưa có tính năng tự đặt lại mật khẩu.

### Chọn tổ chức (Tenant)

Sau khi đăng nhập, **bắt buộc phải chọn tổ chức** để hệ thống biết bạn đang làm việc thuộc đơn vị nào.

- Nhìn vào **thanh bên trái** — có ô chọn Tổ chức
- Chọn tên công ty / đơn vị của bạn từ danh sách thả xuống
- Nếu ô tổ chức trống, bạn sẽ thấy cảnh báo và **không thể sử dụng các tính năng**

> 💡 IT sẽ tạo sẵn tổ chức cho bạn. Nếu không thấy tên đơn vị trong danh sách, liên hệ IT.

Sau khi chọn xong, bạn thấy menu điều hướng với các trang:

```
[ 🏠 Dashboard ]  [ ⚙️ Engine 2 ]  [ 📄 Tài liệu ]
```

---

## 3. Trang chủ — Dashboard

Trang Dashboard hiển thị **tổng quan tình hình** xử lý tài liệu của tổ chức:

| Chỉ số | Ý nghĩa |
|---|---|
| **Tổng tài liệu** | Tổng số file đã nộp vào hệ thống |
| **Báo cáo** | Số báo cáo tổng hợp đã tạo |
| **Tỷ lệ duyệt** | % hồ sơ được duyệt so với tổng |
| **Thời gian xử lý TB** | Trung bình AI xử lý mất bao lâu (phút) |

Phía dưới có:
- **Biểu đồ phân bố trạng thái** — bao nhiêu hồ sơ đang ở từng giai đoạn
- **Danh sách báo cáo gần nhất** — click vào để đi thẳng tới báo cáo đó

> 💡 Nhấn **Làm mới** ở góc trên phải để cập nhật số liệu mới nhất.

---

## 4. Quy trình làm việc từ A đến Z

Dưới đây là cách làm việc đúng thứ tự:

```
Bước 1 → Tạo mẫu (chỉ cần làm 1 lần cho mỗi loại tài liệu)
Bước 2 → Nộp hồ sơ PDF
Bước 3 → Chờ AI xử lý (vài giây đến vài phút)
Bước 4 → Duyệt kết quả
Bước 5 → Tổng hợp báo cáo
Bước 6 → Xuất file
```

Vào **⚙️ Engine 2** từ menu bên trái để truy cập 4 tab:

```
[ ⚙️ Mẫu ]  [ 📤 Hồ sơ ]  [ 🔍 Duyệt ]  [ 📊 Báo cáo ]
```

---

## 5. Tab ⚙️ Mẫu — Quản lý mẫu trích xuất

### Mẫu là gì?

**Mẫu** định nghĩa *loại thông tin* cần rút ra từ tài liệu. Ví dụ: khi xử lý hợp đồng, mẫu sẽ nói rõ "cần lấy: tên bên mua, tên bên bán, ngày ký, giá trị hợp đồng".

Mỗi loại tài liệu thường dùng 1 mẫu riêng. Bạn **chỉ cần tạo mẫu một lần**.

### Badge trạng thái mẫu

Mỗi mẫu trong danh sách có thể hiển thị các badge:

| Badge | Ý nghĩa |
|---|---|
| `N trường` | Số lượng trường dữ liệu |
| `N luật` | Số luật tổng hợp được cấu hình |
| 📝 **Word** | Đã gắn file Word template — có thể xuất Word |
| 🎯 **Auto** | Có cấu hình nhận dạng file tự động theo tên |

### Xem chi tiết mẫu

Nhấn vào tên mẫu để mở rộng, xem danh sách các trường và **phương thức tổng hợp** của từng trường:

| Phương thức | Ý nghĩa |
|---|---|
| `SUM` | Cộng tổng (dùng cho tiền, số lượng) |
| `AVG` | Trung bình cộng |
| `MAX` / `MIN` | Giá trị lớn nhất / nhỏ nhất |
| `COUNT` | Đếm số lượng hồ sơ |
| `CONCAT` | Nối danh sách các giá trị |
| `LAST` | Lấy giá trị của hồ sơ cuối cùng |
| `—` | Không tổng hợp trường này |

### Cách tạo mẫu từ file Word (khuyến nghị)

Nếu bạn có một file Word đã có sẵn các ô điền (ví dụ: `{{ten_nguoi}}`, `{{dia_chi}}`):

1. Vào tab **⚙️ Mẫu** → nhấn **Tạo mẫu mới**
2. Chọn file `.docx` → nhấn **🔍 Scan**
3. Hệ thống phát hiện các trường, hiển thị thống kê:
   - **Trường đơn** — các ô điền bình thường
   - **Danh sách** — các bảng / vòng lặp
4. Đặt **Tên mẫu**
5. **Tinh chỉnh từng trường** (quan trọng):
   - ✓ / ✗ Tick chọn trường muốn giữ lại
   - Đổi **Loại** nếu AI nhận sai (string / number / boolean / array)
   - Chọn **Phương thức tổng hợp** (SUM, AVG, LAST…)
   - Thêm **Mô tả** để dễ nhìn sau này
6. Nhấn **✅ Tạo mẫu**

### Gắn / Thay Word template vào mẫu đã có

Sau khi tạo mẫu, bạn có thể gắn (hoặc thay) file Word dùng để xuất báo cáo:

1. Nhấn vào mẫu để mở rộng
2. Nhấn **📎 Gắn Word template** (hoặc **Thay Word template** nếu đã có)
3. Chọn file `.docx` → nhấn **📤 Upload & Gắn**

> ⚠️ Nếu mẫu chưa có Word template, hệ thống sẽ cảnh báo màu vàng và **tính năng xuất Word sẽ không hoạt động**.

> 💡 **Mẹo:** Đặt tên trường bằng tiếng Anh không dấu để tránh lỗi (VD: `ten_nguoi`, `ngay_ky`, `so_tien`).

---

## 6. Tab 📤 Hồ sơ — Nộp và theo dõi tài liệu

### Nộp hồ sơ

1. Vào tab **📤 Hồ sơ**
2. Phần **"📤 Nạp tài liệu"**:
   - Nhấn **Chọn file** → chọn 1 hoặc nhiều file `.pdf`
   - **Mẫu:** Chọn "🔄 Tự phát hiện mẫu" (AI sẽ tự chọn) hoặc chọn mẫu cụ thể
3. Nhấn **🚀 Nộp hồ sơ**

> ✅ Bạn có thể nộp nhiều file cùng lúc.

### Theo dõi tiến độ

Sau khi nộp, mỗi file xuất hiện trong **"📋 Danh sách hồ sơ"** với các cột:

- **Tên file** — tên file PDF đã nộp
- **Mẫu** — mẫu AI đã áp dụng
- **Kỳ báo cáo** — ngày kỳ báo cáo được gán (nếu có)
- **Trạng thái** — trạng thái hiện tại (xem bảng dưới)
- **Thời gian** — thời điểm nộp

| Trạng thái | Ý nghĩa |
|---|---|
| ⏳ Đang tiếp nhận… | Hệ thống đã nhận file, chờ xử lý |
| 🔄 AI đang đọc tài liệu… | AI đang đọc PDF |
| 🔄 AI đang phân tích chi tiết… | AI đang rút thông tin |
| ✅ Sẵn sàng duyệt | AI xong, **bạn cần vào duyệt** |
| ✅ Đã duyệt | Bạn đã duyệt, hồ sơ sẵn sàng tổng hợp |
| 📊 Có trong báo cáo | Đã được gộp vào báo cáo tổng hợp |
| ⚠️ Cần xem lại | AI gặp vấn đề, cần can thiệp |

> 💡 Nhấn **Làm mới** để cập nhật trạng thái mới nhất.

### Lọc hồ sơ

Dùng 2 bộ lọc phía trên danh sách:
- **Lọc theo trạng thái:** Tất cả / Đang xử lý / Sẵn sàng duyệt / Đã duyệt / Cần xem lại
- **Lọc theo mẫu:** Chọn loại tài liệu cụ thể

---

## 7. Tab 🔍 Duyệt — Kiểm tra và phê duyệt

Đây là bước **quan trọng nhất** — bạn kiểm tra những gì AI đã rút ra và xác nhận (hoặc sửa) trước khi đưa vào báo cáo.

### Quy trình duyệt

1. Vào tab **🔍 Duyệt**
2. Dùng bộ lọc để tìm hồ sơ:
   - **Lọc theo trạng thái:** Tất cả / Sẵn sàng duyệt / Đã duyệt / Cần xem lại
   - **Lọc theo mẫu:** Chọn loại tài liệu
   - **🔎 Ô tìm kiếm:** Gõ tên file để tìm nhanh
3. Nhấn vào một hồ sơ trong danh sách để xem chi tiết

### Panel chi tiết hồ sơ

Khi chọn hồ sơ, phần dưới hiện ra với 2 tab:

**Tab 👁️ Dữ liệu trích xuất:**
- Hiển thị toàn bộ thông tin AI đọc được, dạng trực quan
- Nếu bạn đã chỉnh sửa trước đó, hệ thống hiển thị bản đã chỉnh

**Tab ✏️ Chỉnh sửa JSON:**
- Toàn bộ dữ liệu dạng JSON thô — bạn có thể sửa trực tiếp
- Nhấn **✅ Kiểm tra JSON** để xác nhận cú pháp đúng trước khi duyệt
- Sau khi kiểm tra thành công, nhãn `JSON hợp lệ ✓` xuất hiện màu xanh

> 💡 Dùng tab JSON khi cần sửa chính xác một giá trị mà tab hiển thị không cho sửa trực tiếp.

### Sau khi kiểm tra:

- Nhấn **✅ DUYỆT HỒ SƠ** → hồ sơ chuyển sang "Đã duyệt", sẵn sàng tổng hợp
- Nhấn **❌ TỪ CHỐI** → hồ sơ bị loại (**bắt buộc phải điền ghi chú lý do**)

### Duyệt lại hồ sơ đã duyệt

Nếu cần cập nhật dữ liệu sau khi đã duyệt:
1. Lọc theo "✅ Đã duyệt"
2. Chọn hồ sơ → sửa dữ liệu trong tab JSON
3. Nhấn **✅ DUYỆT HỒ SƠ** lại → dữ liệu được ghi đè

> ⚠️ **Lưu ý:** Chỉ hồ sơ **Đã duyệt** mới được đưa vào báo cáo. Đừng bỏ qua bước này.

---

## 8. Tab 📊 Báo cáo — Tổng hợp và xuất

### Tạo báo cáo thủ công (chọn từng hồ sơ)

Dùng khi bạn muốn tổng hợp một nhóm hồ sơ cụ thể:

1. Vào tab **📊 Báo cáo**
2. Phần **"1️⃣ Tạo báo cáo mới"**
3. Chọn **Mẫu báo cáo**
4. Đặt **Tên báo cáo** (VD: `Tổng hợp tháng 4`)
5. Tích chọn các hồ sơ muốn gộp (hoặc nhấn **☑️ Chọn tất cả**)
6. Nhấn **📊 Tổng hợp X hồ sơ**

### Xem và xuất báo cáo

Phần **"2️⃣ Danh sách báo cáo"**:

1. Chọn báo cáo từ danh sách thả xuống
2. Xem thông tin tổng quan — số hồ sơ, **phiên bản mẫu** tại thời điểm tổng hợp
3. Xem trước dữ liệu tổng hợp
4. Nhấn **xuất** theo định dạng mong muốn:

| Nút | Kết quả |
|---|---|
| 📊 **Excel** | File `.xlsx` bảng tính |
| 📄 **Word (auto)** | File `.docx` tự động theo mẫu đã gắn |
| ⬇️ **JSON** | Dữ liệu thô định dạng JSON |
| 📄 **Word (mẫu upload)** | Bạn tải lên file Word riêng, hệ thống điền vào |

### Dấu hiệu báo cáo lỗi thời ⚠️

Nếu thấy ký hiệu **⚠️** trước tên báo cáo, hoặc thông báo màu vàng **"Báo cáo đã lỗi thời"** — điều này có nghĩa là mẫu trích xuất đã được cập nhật sau khi báo cáo được tạo.

→ Hãy dùng tính năng **🔄 Tổng hợp lại** trong phần Kỳ báo cáo (xem mục 9).

---

## 9. Kỳ báo cáo — Tổng hợp theo chu kỳ

Kỳ báo cáo giúp bạn tổ chức hồ sơ theo **tháng / quý / năm** và tổng hợp toàn bộ cùng lúc — thay vì phải chọn thủ công từng hồ sơ.

### Tạo kỳ báo cáo

1. Vào tab **� Báo cáo** → phần **"🗓️ Kỳ báo cáo"**
2. Nhấn **➕ Tạo kỳ mới**
3. Điền thông tin:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **Mẫu trích xuất** | Loại tài liệu áp dụng | `Hợp đồng mua bán` |
| **Nhãn kỳ** | Tên để phân biệt kỳ | `Q2-2026`, `Tháng 4/2026` |
| **Loại kỳ** | Tháng / Quý / Năm / Tùy chỉnh | `Quý` |
| **Từ ngày** | Ngày bắt đầu kỳ | `01/04/2026` |
| **Đến ngày** | Ngày kết thúc kỳ | `30/06/2026` |

4. Nhấn **🗓️ Tạo kỳ**

### Tổng hợp kỳ

1. Chọn kỳ từ danh sách thả xuống
2. (Tuỳ chọn) Đặt tên báo cáo
3. Nhấn **📊 Tổng hợp kỳ** → hệ thống tự gom toàn bộ hồ sơ **đã duyệt** trong khoảng thời gian đó
4. Báo cáo tạo xong → xuất файл bình thường

### Tổng hợp lại kỳ

Khi có thêm hồ sơ mới được duyệt, hoặc mẫu trích xuất được cập nhật:

1. Chọn kỳ đã có
2. Nhấn **🔄 Tổng hợp lại** → báo cáo cũ được thay thế bằng phiên bản mới nhất

### Đóng kỳ

Khi kỳ báo cáo đã hoàn tất và không cho phép sửa thêm:

1. Chọn kỳ cần đóng
2. Nhấn **🔒 Đóng kỳ**

> Kỳ đã đóng vẫn có thể xem và xuất báo cáo, nhưng **không thể tổng hợp mới** (chỉ có thể tổng hợp lại).

---

## 10. Trang 📄 Tài liệu

Truy cập từ menu bên trái → **📄 Tài liệu**.

Trang này hiển thị **toàn bộ file đã được upload** lên hệ thống (từ tất cả các lần nộp hồ sơ), kèm theo:
- Tên file
- Ngày tải lên
- Tags (nếu có)

Đây là trang **chỉ xem** — dùng để tra cứu lại tài liệu gốc đã nộp.

> 💡 Muốn xử lý lại một tài liệu, hãy nộp lại file đó trong tab **📤 Hồ sơ**.

---

## 11. Các trạng thái hồ sơ

Sơ đồ vòng đời một hồ sơ:

```
Nộp lên
   ↓
⏳ Đang tiếp nhận
   ↓
🔄 AI đang xử lý (đọc → phân tích → chi tiết)
   ↓
✅ Sẵn sàng duyệt  ──→  [Bạn xem]  ──→  🚫 Từ chối
   ↓ (Bạn duyệt)
✅ Đã duyệt
   ↓ (Tổng hợp báo cáo)
📊 Có trong báo cáo
```

**Trường hợp đặc biệt:**

| Tình huống | Xử lý |
|---|---|
| ⚠️ Cần xem lại | AI không đọc được file. Thử dùng file scan chất lượng cao hơn. Có thể nhấn nút **Retry** (↻) |
| 🚫 Từ chối | Hồ sơ bị loại. Nếu muốn xử lý lại, cần nộp file mới |
| 📊 Có trong báo cáo | Hồ sơ đang nằm trong 1 báo cáo. Nếu xóa báo cáo đó, hồ sơ sẽ quay về trạng thái "Đã duyệt" |

---

## 12. Câu hỏi thường gặp

**❓ Nộp file xong rồi nhưng không thấy gì?**
→ Nhấn nút **Làm mới** trong tab � Hồ sơ. Nếu vẫn không thấy sau 2 phút, liên hệ IT.

**❓ AI đọc sai nhiều trường quá, phải làm sao?**
→ Sửa tay trong tab � Duyệt rồi duyệt bình thường. Nếu lỗi lặp đi lặp lại, mẫu trích xuất cần được IT điều chỉnh.

**❓ File PDF bị từ chối / AI không đọc được?**
→ Đảm bảo file PDF:
- Không bị mã hóa / khóa mật khẩu
- Không quá mờ hoặc chụp nghiêng (nếu là bản scan)
- Dung lượng dưới 50MB

**❓ Tổng hợp rồi mà xuất Excel bị thiếu cột?**
→ Mẫu trích xuất có thể thiếu trường. Liên hệ IT để bổ sung trường vào mẫu, sau đó tổng hợp lại kỳ.

**❓ Có thể xóa hồ sơ không?**
→ Được, nhấn icon thùng rác 🗑️ trong tab � Hồ sơ. Lưu ý: hồ sơ đang ở trạng thái **Đang xử lý** thì không xóa được, chờ xong mới xóa.

**❓ Tôi đã xuất báo cáo rồi, muốn xuất lại với dữ liệu mới hơn?**
→ Dùng **🔄 Tổng hợp lại** trong phần Kỳ báo cáo, sau đó xuất lại.

**❓ Nhiều người cùng dùng, ai duyệt là xong không?**
→ Đúng. Bất kỳ ai trong cùng tổ chức (tenant) cũng có thể duyệt. Không có phân quyền theo cấp bậc trong phiên bản hiện tại.

**❓ Sao tôi không thấy nút Xuất Word?**
→ Mẫu chưa được gắn Word template. Vào tab **⚙️ Mẫu** → mở rộng mẫu đó → nhấn **📎 Gắn Word template**.

**❓ Từ chối hồ sơ mà không điền ghi chú được không?**
→ Không, ghi chú là **bắt buộc** khi từ chối. Hệ thống sẽ báo lỗi nếu để trống.

**❓ Tôi sửa JSON sai rồi, làm sao khôi phục?**
→ Nhấn **✅ Kiểm tra JSON** trước khi duyệt. Nếu sai cú pháp, hệ thống báo lỗi và không cho duyệt. Bạn có thể copy lại từ tab **👁️ Dữ liệu trích xuất** để đối chiếu.

---

## 13. Khi nào cần liên hệ IT

Liên hệ bộ phận kỹ thuật khi gặp các tình huống sau:

| Tình huống | Mức độ |
|---|---|
| Không đăng nhập được dù mật khẩu đúng | 🔴 Khẩn |
| Hồ sơ mắc kẹt ở trạng thái **🔄 Đang xử lý** quá 30 phút | 🟡 Bình thường |
| AI liên tục đọc sai 1 loại thông tin cụ thể | 🟡 Bình thường |
| Muốn thêm loại tài liệu mới (mẫu mới) | 🟢 Kế hoạch |
| Muốn thêm cột / trường trong báo cáo Excel | 🟢 Kế hoạch |
| Trang trắng / lỗi 500 / màn hình đỏ | 🔴 Khẩn |

**Thông tin cần cung cấp khi liên hệ IT:**
1. Tên tài khoản đang dùng
2. Tên hồ sơ / báo cáo gặp lỗi
3. Chụp màn hình lỗi (nếu có)
4. Thời điểm xảy ra

---

*Tài liệu này được cập nhật theo phiên bản hệ thống tháng 4/2026.*
*Mọi thắc mắc vui lòng liên hệ đội kỹ thuật.*
