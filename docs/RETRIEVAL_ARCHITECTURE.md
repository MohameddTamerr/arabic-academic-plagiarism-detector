# وثيقة المعمارية الهندسية لاسترجاع المرشحين بالملايين (Two-Stage Candidate Retrieval Architecture)

---

## 1. خط الأنابيب المفاهيمي للفحص (Candidate Filtering Pipeline)

```
[ نص البحث المدخل (Query Document) ]
                  |
                  v
       [ التقطيع إلى جمل / فقرات ] (Document Segmentation)
                  |
                  v
[ المرحلة 1: الاسترجاع السريع بالقوائم المقلوبة والتطابق الإحداثي ] 
   (Fast Filtered Inverted Index + Coordinate Boost -> Internal Top-300)
                  |
                  v
[ المرحلة 2: إعادة الترتيب المعجمي الخفيف ]
   (Fast Lexical Jaccard Reranking -> Top-50 Only)
                  |
                  v
[ أفضل K مرشح مقيد حصراً: Top-K <= 50 ] (Bounded Final Candidate Set)
                  |
                  v
[ محرك الفحص الدقيق والعميق ] (Existing Detection Engine)
   - مطابقة المتواليات الحرفية (Shingle / Jaccard Matching)
   - كشف إعادة الصياغة اللفظية (TF-IDF Cosine Similarity)
   - فلترة الاستشهادات المنقحة (Refined Citation Filter)
   - استبعاد ديباجات النصوص الشائعة (Span-Level Common-Text Filter)
                  |
                  v
[ تقرير الفحص المعتمد بضمانات سلامة SHA-256 ] (Finalized Tamper-Evident Report)
```

---

## 2. كسر التعقيد الحسابي الشامل $O(N \times M)$

- **المقارنة الشاملة البطيئة:** فحص مستند به $M$ مقطع ضد قاعدة مراجع تضم $N$ مقطع كان يتطلب إجراء $M \times N$ عملية مقارنة بالغة التكلفة (Jaccard + TF-IDF) لكل فحص.
- **الحل عبر استرجاع المرشحين ثنائي المرحلة (Two-Stage Candidate Retrieval):**
  - استعلام الفهرس المقلوب بالمفردات ومتواليات الحروف النادرة بزمن محكوم بعدد مصطلحات الاستعلام وطول قوائم البوستينغ المشذبة.
  - اختيار مجموعة مرشحين داخلية $K_{\text{internal}} = 300$.
  - إعادة ترتيب معجمية سريعة واقتطاع أفضل $K_{\text{final}} \le 50$ مرشحاً فقط.
  - تعقيد المعالجة الدقيقة للمطابق يصبح $O(M \times K)$ حيث $K=50$ سقف صارم وثابت.

---

## 3. معادلات الترتيب ثنائي المرحلة (Two-Stage Ranking Mathematics)

### المرحلة الأولى: وزن BM25-IDF مع التعزيز الإحداثي (Stage 1 Score)

$$\text{IDF}(w) = \ln\left(1.0 + \frac{N_{\text{total}} - \text{df}(w) + 0.5}{\text{df}(w) + 0.5}\right)$$

$$\text{Score}_{\text{base}}(s) = \sum_{w \in Q \cap s} \text{IDF}(w) + \sum_{c \in Q_{\text{cng}} \cap s} 0.5 \cdot \text{IDF}(c)$$

$$\text{Score}_{\text{Stage1}}(s) = \text{Score}_{\text{base}}(s) \times \left(1.0 + 1.5 \times (m(s) - 1)\right) \quad \text{حيث } m(s) \text{ عدد مصطلحات الاستعلام المتطابقة}$$

### المرحلة الثانية: إعادة الترتيب المعجمي (Stage 2 Final Score)

$$\text{Final Retrieval Score}(s) = \text{Score}_{\text{Stage1}}(s) + 5.0 \times \text{Jaccard}_{\text{lexical}}(Q_{\text{words}}, s_{\text{words}})$$

---

## 4. الالتزام بالعقد الهندسي لسلامة الكشف

- **الاستقلال التام بين الاسترجاع والقرار الأكاديمي:** درجة الاسترجاع (Retrieval Score) هي أداة ترتيب مرشحين فقط ولا تمثل نسبة استلال ولا تتدخل في القرار الأكاديمي.
- **سقف المرشحين:** لا يُرسل لمحرك Jaccard و TF-IDF سوى $K \le 50$ مرشحاً كحد أقصى ثابت.
