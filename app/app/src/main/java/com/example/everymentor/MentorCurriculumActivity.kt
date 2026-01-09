package com.example.everymentor

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.example.everymentor.data.ApiClient
import com.example.everymentor.data.CertificationVerifyRequest
import kotlinx.coroutines.launch

class MentorCurriculumActivity : AppCompatActivity() {

    private val PICK_CERT_REQUEST = 1001

    // 여러 개 선택을 위해 리스트로 변경
    private val selectedCertUris = mutableListOf<Uri>()

    private lateinit var tvUploadGuide: TextView
    private lateinit var btnUpload: Button
    private lateinit var btnVerify: Button
    private lateinit var btnGenerate: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_mentor_curriculum)

        tvUploadGuide = findViewById(R.id.tvUploadGuide)
        btnUpload = findViewById(R.id.btnUploadCertificate)
        btnVerify = findViewById(R.id.btnRegisterCertificate)
        btnGenerate = findViewById(R.id.btnGenerateAiCurriculum)

        // 1) 자격증 이미지(1개 또는 여러 개) 선택
        btnUpload.setOnClickListener {
            openFilePicker()
        }

        // 2) 선택한 이미지들을 verify API 로 보내서 커리큘럼 받기
        btnVerify.setOnClickListener {
            if (selectedCertUris.isEmpty()) {
                Toast.makeText(this, "먼저 자격증 이미지를 선택하세요.", Toast.LENGTH_SHORT).show()
            } else {
                // 여기서는 간단하게: 여러 장을 순서대로 보내고,
                // 마지막 응답 커리큘럼을 화면에 표시
                selectedCertUris.forEach { uri ->
                    callVerifyApi(uri)
                }
            }
        }

        // 3) 추가 커리큘럼 기능용 (지금은 토스트만)
        btnGenerate.setOnClickListener {
            Toast.makeText(this, "커리큘럼 추가 기능은 나중에 연결 예정입니다.", Toast.LENGTH_SHORT).show()
        }
    }

    // ----- 이미지 선택 (여러 장 허용) -----
    private fun openFilePicker() {
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            type = "image/*"
            addCategory(Intent.CATEGORY_OPENABLE)
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)   // 여러 개 선택 허용
        }
        startActivityForResult(
            Intent.createChooser(intent, "자격증 이미지를 선택하세요"),
            PICK_CERT_REQUEST
        )
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == PICK_CERT_REQUEST && resultCode == Activity.RESULT_OK) {
            selectedCertUris.clear()

            val clipData = data?.clipData
            if (clipData != null) {
                // 여러 개 선택한 경우
                for (i in 0 until clipData.itemCount) {
                    val uri = clipData.getItemAt(i).uri
                    selectedCertUris.add(uri)
                }
            } else {
                // 하나만 선택한 경우
                data?.data?.let { uri ->
                    selectedCertUris.add(uri)
                }
            }

            if (selectedCertUris.isNotEmpty()) {
                tvUploadGuide.text = "자격증 이미지 ${selectedCertUris.size}개 선택 완료"
                Toast.makeText(this, "이미지 선택 완료", Toast.LENGTH_SHORT).show()
            }
        }
    }

    // ----- Uri -> Base64 -> /api/certifications/verify 호출 -----
    private fun callVerifyApi(uri: Uri) {
        lifecycleScope.launch {
            try {
                // 1) 이미지 바이트 읽기
                val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes == null) {
                    Toast.makeText(this@MentorCurriculumActivity, "이미지 읽기 실패", Toast.LENGTH_SHORT).show()
                    return@launch
                }

                // 2) Base64 인코딩
                val base64 = Base64.encodeToString(bytes, Base64.NO_WRAP)

                // 3) 요청 객체 (type 값은 백엔드 enum에 맞춰 수정)
                val request = CertificationVerifyRequest(
                    type = "HEALTH_INSURANCE",
                    imageBase64 = base64
                )

                // 4) API 호출
                val res = ApiClient.api.verifyCertification(request)

                if (res.success) {
                    val curriculum = res.extractedText ?: "커리큘럼 정보가 없습니다."
                    // 여러 장 보낼 때는 마지막 응답으로 덮어씀
                    tvUploadGuide.text = curriculum
                } else {
                    Toast.makeText(
                        this@MentorCurriculumActivity,
                        "검증 실패: ${res.errorMessage}",
                        Toast.LENGTH_SHORT
                    ).show()
                }

            } catch (e: Exception) {
                e.printStackTrace()
                Toast.makeText(
                    this@MentorCurriculumActivity,
                    "API 에러: ${e.message}",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }
}
