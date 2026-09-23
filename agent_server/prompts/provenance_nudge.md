<!-- Sent to the model as a message, mid-turn, when it produced an answer
     having called no tool at all. Never written to state, so it reaches
     neither the transcript nor the next turn nor the person reading.

     Not part of `system_prompt.md`: at the start of a turn there is no answer
     to comment on, and this is a reply to one rather than a standing rule.

     Phrased to be answerable both ways. A question that needs data is sent to
     get it; one that does not is sent to say so, so a correct refusal is not
     argued out of itself. -->

Kamu menjawab tanpa memanggil tool apa pun pada giliran ini, jadi jawaban itu
belum bersandar pada data. Jika jawabanmu memuat angka atau pernyataan tentang
isi tabel tiket, jalankan query untuk memastikannya — jangan mengandalkan
jawaban dari giliran sebelumnya. Jika pertanyaan ini memang tidak membutuhkan
data tiket, tidak apa-apa.

Apa pun pilihanmu, tulis ulang jawaban untuk pertanyaan pengguna secara utuh
dan berdiri sendiri. Jangan menyebut, membahas, atau menjawab pesan ini —
pengguna tidak melihatnya.
