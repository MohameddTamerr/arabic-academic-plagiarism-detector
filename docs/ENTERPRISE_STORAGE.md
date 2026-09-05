# دليل تخزين الوثائق المؤسسية (Enterprise Content-Addressed Storage)

---

## 1. هيكلية التخزين الموجه بالمحتوى (Content-Addressed Storage Layout)

لتفادي وضع مئات الآلاف من الملفات في مجلد واحد (مما يسبب انهيار أداء نظام الملفات وتجاوز حدود inodes)، تم اعتماد تقسيم ذري على مستويين بناءً على تجزئة SHA-256 لبايتات الملف:

```
storage/
  documents/
    ab/                      <-- الحرفان الأول والثاني من تجزئة SHA-256
      cd/                    <-- الحرفان الثالث والرابع من تجزئة SHA-256
        abcdef1234567890.../ <-- التجزئة الكاملة (64 حرفاً)
          content.bin        <-- المحتوى الأصلي للوثيقة
          metadata.json      <-- البيانات الوصفية (الحجم، الامتداد، الاسم الأصلي)
```

### المزايا الهندسية:
1. **توزيع متوازن (Bounded Fan-out):** سعة قصوى تصل لـ 256 × 256 = 65,536 مجلداً فرعياً، مما يضمن أداء سريعاً جداً لنظام التشغيل حتى مع ملايين الملفات.
2. **إلغاء التكرار الفيزيائي الآمن (Safe Physical Deduplication):** إذا رفع مستخدمان نفس الملف، يُخزن الملف مادياً مرة واحدة فقط، مع إنشاء سجلين منفصلين تماماً في قاعدة البيانات لكل مستخدم لضمان خصوصية البيانات وصلاحيات الوصول.
3. **إدارة دورة الحياة بالارتباط (Reference-Aware Lifecycle):** حذف أحد الأبحاث لا يحذف الملف المادي إذا كان هناك بحث آخر أو وثيقة مرجعية تشير لنفس التجزئة.

---

## 2. واجهة التخزين الموحدة (Storage Backend Abstraction Interface)

```python
class StorageBackend(ABC):
    @abstractmethod
    def put(self, stream_or_bytes, content_hash: str, ext: str, metadata: dict) -> dict: ...

    @abstractmethod
    def get(self, content_hash: str) -> bytes: ...

    @abstractmethod
    def open(self, content_hash: str, mode: str = 'rb'): ...

    @abstractmethod
    def exists(self, content_hash: str) -> bool: ...

    @abstractmethod
    def delete(self, content_hash: str) -> bool: ...

    @abstractmethod
    def stat(self, content_hash: str) -> dict: ...

    @abstractmethod
    def verify_hash(self, content_hash: str) -> bool: ...
```
