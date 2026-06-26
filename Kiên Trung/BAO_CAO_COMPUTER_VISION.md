# Báo Cáo: Phân Vùng Ảnh (Image Segmentation) — Lý Thuyết & Lý Do Lựa Chọn

**Dự án:** AI Trợ Lý Drone Tự Hành Cho Khảo Sát & Giám Sát Nông Nghiệp (Team 079 — Autonomous Drones)

**Phạm vi:** Tập trung vào **phân vùng ngữ nghĩa ảnh** (semantic segmentation) — cơ sở lý thuyết của từng lựa chọn kỹ thuật và *vì sao* các lựa chọn đó phù hợp với đặc thù dự án này. (Không bàn về tiền xử lý dữ liệu hay lập kế hoạch đường bay.)

---

## 1. Vai trò của phân vùng ảnh trong dự án

Drone khảo sát nông nghiệp cần trả lời một câu hỏi nền tảng trước khi làm bất cứ điều gì khác: **"Mỗi vị trí trên cánh đồng này là gì?"** — đâu là đất canh tác cần bay khảo sát, đâu là rừng/nước/công trình phải tránh, đâu là đường đi. Câu trả lời phải ở **mức từng pixel** vì lộ trình bay và ước tính độ phủ đòi hỏi ranh giới chính xác.

Khối phân vùng ảnh chính là khâu biến một bức ảnh không ảnh thô thành **bản đồ ngữ nghĩa** (mỗi pixel mang một nhãn lớp), làm nền tảng dữ liệu cho toàn bộ hệ thống. Đây là lý do nó là khâu được đầu tư kỹ thuật nhiều nhất trong khối thị giác máy tính.

Mã nguồn chính: `Kiên Trung/Segmentation models training codes/train.py`.

---

## 2. Vì sao chọn Semantic Segmentation (chứ không phải Classification hay Detection)?

Trong thị giác máy tính có ba mức bài toán nhận dạng, và việc chọn đúng mức là quyết định kiến trúc đầu tiên:

| Bài toán | Đầu ra | Đặt vào dự án này thì sao? |
|----------|--------|---------------------------|
| **Image Classification** | Một nhãn cho *cả* ảnh | Vô dụng — biết "ảnh có cánh đồng" không cho biết cánh đồng *ở đâu*, không lập được đường bay |
| **Object Detection** | Bounding box quanh từng đối tượng | Không phù hợp — cánh đồng/rừng/nước là vùng có hình dạng tự do, bất quy tắc; hộp chữ nhật không mô tả nổi ranh giới ruộng |
| **Semantic Segmentation** | Nhãn lớp cho *từng pixel* | ✅ Đúng nhu cầu — cho ranh giới chính xác đến từng pixel của vùng canh tác và vật cản |

**Lý do cốt lõi:** đối tượng quan tâm trong dự án (ruộng đồng, rừng, mặt nước) là các **vùng liên tục hình dạng bất kỳ** (amorphous regions), không phải vật thể đếm được có hình hộp. Chỉ segmentation mới biểu diễn được "ranh giới mềm" này. Hơn nữa, các bước sau (tính % độ phủ, xác định vùng cần bay) bản chất là phép toán *trên mặt nạ pixel* — nên đầu ra của segmentation khớp trực tiếp, không cần chuyển đổi.

---

## 3. Vì sao chọn kiến trúc U-Net?

Sau khi chốt bài toán là segmentation, câu hỏi tiếp theo là chọn kiến trúc mạng nào. Dự án chọn **U-Net** (Ronneberger et al., 2015).

### 3.1. Cấu trúc U-Net

U-Net là mạng encoder–decoder đối xứng hình chữ U:

- **Encoder (đường co — contracting path):** liên tục giảm độ phân giải không gian, tăng số kênh đặc trưng. Vai trò: trích xuất ngữ nghĩa trừu tượng — "*cái gì* xuất hiện trong ảnh" (đây là cánh đồng, kia là rừng).
- **Decoder (đường giãn — expanding path):** dần khôi phục độ phân giải về kích thước ảnh gốc. Vai trò: định vị — "*ở đâu*", tái tạo mặt nạ pixel.
- **Skip connections (kết nối tắt):** đặc trưng độ phân giải cao từ encoder được nối thẳng sang decoder cùng mức.

### 3.2. Vì sao U-Net phù hợp với dự án này

**(1) Skip connection giữ ranh giới sắc nét — yếu tố sống còn.**
Trong một mạng encoder–decoder thuần, thông tin không gian chi tiết bị mất khi đi qua "bottleneck" (tầng nén nhất). Kết quả là biên dự đoán bị nhoè. U-Net giải quyết bằng cách *bơm thẳng* feature map độ phân giải cao từ encoder sang decoder, khôi phục chi tiết biên. Với dự án này, **độ sắc nét của ranh giới ruộng quyết định trực tiếp chất lượng lộ trình bay** — biên nhoè đồng nghĩa drone bay sai mép cánh đồng hoặc lấn vào vật cản. Đây là lý do quan trọng nhất.

**(2) Hiệu quả trên dữ liệu hạn chế.**
U-Net ra đời cho ảnh y sinh — bối cảnh *rất ít dữ liệu gán nhãn*. Dự án nông nghiệp cũng vậy: nhãn pixel-level cho ảnh không ảnh rất đắt để tạo. U-Net nổi tiếng đạt kết quả tốt với lượng mẫu khiêm tốn, đúng tình huống của dự án.

**(3) Đã được kiểm chứng, ổn định, dễ triển khai.**
U-Net là kiến trúc chuẩn mực, được hỗ trợ sẵn trong thư viện `segmentation_models_pytorch` (chỉ vài dòng để dựng). Với một dự án sinh viên có thời gian giới hạn, chọn kiến trúc *đã được chứng minh* thay vì thử nghiệm kiến trúc mới lạ là quyết định kỹ thuật hợp lý — giảm rủi ro, dồn công sức vào phần thực sự khó (xử lý mất cân bằng lớp, mục 5).

---

## 4. Vì sao chọn encoder ResNet34 + Transfer Learning?

U-Net cho phép thay encoder bằng một backbone mạnh hơn. Dự án dùng **ResNet34 đã pretrain trên ImageNet**:

```python
model = smp.Unet(
    encoder_name    = "resnet34",
    encoder_weights = "imagenet",   # transfer learning
    in_channels     = 3,
    classes         = 5,
)
```

### 4.1. Vì sao là ResNet (residual connection)?

ResNet đưa ra **kết nối tắt phần dư** `y = F(x) + x`, giải quyết bài toán *vanishing gradient* khiến mạng sâu khó huấn luyện. Nhờ đó encoder có thể sâu mà vẫn học ổn định, trích xuất được đặc trưng phân cấp phong phú hơn encoder gốc của U-Net.

### 4.2. Vì sao là ResNet34 (không phải ResNet18 hay ResNet101)?

Đây là cân bằng giữa **năng lực biểu diễn** và **chi phí**:
- ResNet18: nhẹ nhưng có thể thiếu năng lực cho ảnh không ảnh nhiều texture phức tạp.
- ResNet101/152: mạnh nhưng nặng, dễ overfit trên dữ liệu hạn chế, huấn luyện chậm, khó vừa GPU phổ thông.
- **ResNet34: "điểm ngọt"** — đủ sâu để học đặc trưng tốt, đủ nhẹ để huấn luyện nhanh và triển khai được trên phần cứng vừa phải. Phù hợp ràng buộc tài nguyên của dự án và mục tiêu hướng tới khả năng chạy gần biên (edge).

### 4.3. Vì sao Transfer Learning (pretrain ImageNet) lại đặc biệt quan trọng ở đây?

**Lý thuyết:** các tầng đầu của mạng học những đặc trưng thị giác *phổ quát* — cạnh, góc, gradient màu, texture — gần như độc lập với miền dữ liệu. Một mô hình đã học những đặc trưng này trên ImageNet (hàng triệu ảnh) không cần học lại từ đầu.

**Vì sao quan trọng với dự án:** nhãn ảnh không ảnh nông nghiệp khan hiếm. Nếu khởi tạo trọng số ngẫu nhiên, mạng phải học cả đặc trưng cơ bản lẫn đặc trưng chuyên ngành từ một tập dữ liệu nhỏ → dễ overfit, hội tụ chậm, kết quả kém. Transfer learning cho phép "đứng trên vai" tri thức ImageNet và chỉ tinh chỉnh phần chuyên ngành → **hội tụ nhanh hơn và độ chính xác cao hơn rõ rệt** với cùng lượng dữ liệu. Đây là một trong những lựa chọn đem lại lợi ích lớn nhất so với công sức bỏ ra.

---

## 5. Vì sao thiết kế hàm mất mát kết hợp 4 thành phần?

Đây là phần lý thuyết quan trọng nhất, vì nó trực tiếp giải bài toán khó nhất của dự án: **mất cân bằng lớp nghiêm trọng**.

### 5.1. Bản chất vấn đề

Ảnh nông thôn có phân bố lớp cực lệch (thống kê thực tế của tập train):

```
farmland : 72.33%   |  woodland : 20.58%  |  water : 4.13%
road     :  1.86%   |  building :  1.10%   ← cực hiếm
```

Một mô hình huấn luyện với loss thông thường sẽ phát hiện ra mẹo "lười": chỉ cần đoán *mọi pixel là farmland* đã đúng ~72%. Nó sẽ **bỏ qua hoàn toàn đường và công trình** — nhưng đây lại chính là các vật cản drone phải tránh. Loss tiêu chuẩn không trừng phạt đủ mạnh việc bỏ sót lớp hiếm.

### 5.2. Giải pháp: kết hợp 4 loss bổ trợ nhau

```
Total = w_ce·CE + w_dice·Dice + w_focal·Focal + w_lovasz·Lovász
        (w_ce=0.2, w_dice=0.4, w_focal=0.2, w_lovasz=0.2)
```

Mỗi thành phần khắc phục một điểm yếu, được chọn *có chủ đích*:

**1. Weighted Cross-Entropy — vì sao cần?**
CE chuẩn phạt sai từng pixel độc lập. Thêm **trọng số lớp nghịch đảo tần suất** để mỗi lỗi ở lớp hiếm "đắt" hơn nhiều:
```python
CLASS_WEIGHTS = [0.15, 4.00, 0.80, 1.50, 4.00]
#                 bg   build  wood  water road
```
→ Buộc mô hình *quan tâm* tới building/road dù chúng ít. Đây là tuyến phòng thủ trực tiếp nhất chống mất cân bằng.

**2. Dice Loss — vì sao cần thêm?**
CE đo theo *số pixel*; Dice đo theo *tỉ lệ vùng chồng lấp* `2|A∩B|/(|A|+|B|)`. Vì Dice chuẩn hoá theo kích thước vùng, nó **không bị lớp đa số áp đảo** — một lớp nhỏ và một lớp lớn đóng góp tương đương vào loss. Bổ sung góc nhìn mà CE thiếu.

**3. Focal Loss (γ=2) — vì sao cần thêm?**
Vấn đề còn lại: vô số pixel farmland *dễ* đoán làm "loãng" tín hiệu học. Focal nhân hệ số `(1−p)^γ` để **giảm trọng số pixel đã đoán đúng tự tin**, dồn sự chú ý của mô hình vào *pixel khó* — biên đường mảnh, công trình nhỏ. Chuyển trọng tâm học từ "dễ" sang "khó".

**4. Lovász-Softmax Loss — vì sao là điểm nâng cao?**
Chỉ số đánh giá cuối cùng là IoU, nhưng IoU *không khả vi* nên không thể tối ưu trực tiếp bằng gradient descent. Lovász-Softmax (Berman et al., 2018) là **hàm thay thế lồi, khả vi, xấp xỉ trực tiếp IoU theo từng lớp**. Nó đặc biệt cứu các lớp *mỏng* như đường — nơi sai lệch vài pixel làm IoU sụt mạnh mà các loss trung bình pixel không "thấy". Đây là loss tinh chỉnh đúng vào mục tiêu đánh giá.

**Triết lý tổng thể:** không có loss đơn lẻ nào giải trọn vẹn mất cân bằng. CE cho tín hiệu pixel-wise rõ; Dice và Lovász tối ưu chất lượng vùng/IoU; Focal điều hướng chú ý vào mẫu khó. Kết hợp có trọng số tạo nên một hàm mục tiêu cân bằng — đây là nơi thể hiện hiểu biết sâu nhất về bài toán.

### 5.3. Củng cố thêm ở mức lấy mẫu

Song song với loss, dự án dùng `WeightedRandomSampler` để **tăng xác suất lấy mẫu các tile chứa lớp hiếm** (building/road). Như vậy mất cân bằng bị tấn công đồng thời ở *hai mặt trận*: hàm phạt (loss) và phân phối dữ liệu đưa vào (sampler) — một chiến lược toàn diện.

---

## 6. Vì sao đánh giá bằng mean IoU?

Việc chọn đúng *thước đo* cũng quan trọng như chọn mô hình.

- **Pixel accuracy** (tỉ lệ pixel đúng) **không phù hợp**: với phân bố lệch, đoán toàn farmland đã ~72% accuracy nhưng mô hình vô dụng. Accuracy bị lớp đa số che lấp.
- **IoU theo từng lớp** = `|dự đoán ∩ thực tế| / |dự đoán ∪ thực tế|`, và **mean IoU** lấy trung bình qua tất cả lớp. Vì *mỗi lớp đóng góp ngang nhau*, mIoU **phạt nặng việc bỏ sót lớp hiếm** — đúng điều ta cần đo. Một mô hình bỏ qua đường sẽ có IoU lớp đường ≈ 0, kéo mIoU xuống ngay, phơi bày điểm yếu mà accuracy giấu đi.

→ mIoU là thước đo *trung thực* với bài toán mất cân bằng, nên là tiêu chí chọn checkpoint tốt nhất.

**Kết quả thực tế:** mô hình đạt **validation mIoU = 0.8233** (epoch 22) — tốt cho bài toán 5 lớp lệch mạnh, xác nhận các lựa chọn ở trên là đúng đắn.

---

## 7. Tổng kết — chuỗi quyết định và lý do

| Quyết định | Lựa chọn | Lý do cốt lõi cho dự án này |
|------------|----------|------------------------------|
| Loại bài toán | Semantic Segmentation | Cần ranh giới từng pixel của vùng hình dạng tự do (ruộng, rừng, nước) |
| Kiến trúc | U-Net | Skip connection giữ biên sắc nét; hiệu quả trên dữ liệu ít; đã kiểm chứng |
| Encoder | ResNet34 | Cân bằng năng lực ↔ chi phí; residual chống vanishing gradient |
| Khởi tạo | Pretrain ImageNet (transfer learning) | Bù cho dữ liệu chuyên ngành khan hiếm → hội tụ nhanh, chính xác hơn |
| Hàm mất mát | CE có trọng số + Dice + Focal + Lovász | Giải mất cân bằng lớp đa tầng — bài toán khó nhất |
| Lấy mẫu | WeightedRandomSampler | Củng cố chống mất cân bằng ở mức phân phối dữ liệu |
| Đánh giá | mean IoU | Thước đo trung thực với phân bố lớp lệch |

**Kết luận:** Mọi lựa chọn kỹ thuật của khối phân vùng ảnh đều xuất phát từ hai đặc thù cốt lõi của dự án — **(1) nhu cầu ranh giới chính xác đến từng pixel** để phục vụ bay khảo sát, và **(2) dữ liệu nông nghiệp vừa khan hiếm vừa mất cân bằng lớp nghiêm trọng**. U-Net + ResNet34 pretrain giải quyết vế thứ nhất và bài toán dữ liệu ít; thiết kế loss kết hợp + oversampling + đánh giá bằng mIoU giải quyết vế mất cân bằng. Sự nhất quán giữa *đặc thù bài toán* và *từng lựa chọn kỹ thuật* chính là điểm mạnh của thiết kế này.

---

*Báo cáo lập ngày 26/06/2026.*
