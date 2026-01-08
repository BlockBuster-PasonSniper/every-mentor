package com.example.everymentor

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts

class MentorActivity : AppCompatActivity() {

    // 사용자가 선택한 PDF 파일들의 Uri 리스트
    private val selectedPdfUris = mutableListOf<Uri>()

    // Activity Result API: PDF 여러 개 선택
    private val pickPdfLauncher =
        registerForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
            if (uris.isNullOrEmpty()) {
                Toast.makeText(this, "선택된 파일이 없습니다.", Toast.LENGTH_SHORT).show()
                return@registerForActivityResult
            }

            // 기존 목록 초기화 후 새로 채우기
            selectedPdfUris.clear()
            selectedPdfUris.addAll(uris)

            // 읽기 권한 유지 (앱 재실행 전까지)
            uris.forEach { uri ->
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            }

            // 화면에 파일 이름 목록 표시
            displaySelectedFiles()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_mentor)

        val tvSelectedFiles: TextView = findViewById(R.id.tvSelectedFiles)
        val btnPickPdf: Button = findViewById(R.id.btnPickPdf)
        val btnGenerateCurriculum: Button = findViewById(R.id.btnGenerateCurriculum)

        // PDF 선택 버튼 클릭
        btnPickPdf.setOnClickListener {
            openPdfPicker()
        }

        // AI 커리큘럼 생성 버튼 클릭
        btnGenerateCurriculum.setOnClickListener {
            if (selectedPdfUris.isEmpty()) {
                Toast.makeText(this, "자격증을 먼저 선택해 주세요.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // 서버/AI API 호출
            // sendPdfsToServer(selectedPdfUris) ? 여긴 어케해야할라나

            Toast.makeText(
                this,
                "AI 커리큘럼 생성 요청을 보냈다고 가정하고, 나중에 여기서 결과 화면으로 이동.",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    private fun openPdfPicker() {
        // Storage Access Framework를 이용해 PDF 여러 개 선택
        val mimeTypes = arrayOf("application/pdf")

        pickPdfLauncher.launch(mimeTypes)
    }

    private fun displaySelectedFiles() {
        val tvSelectedFiles: TextView = findViewById(R.id.tvSelectedFiles)

        val names = selectedPdfUris.map { uri ->
            getFileNameFromUri(uri) ?: uri.toString()
        }

        tvSelectedFiles.text = names.joinToString(separator = "\n")
    }

    // Uri에서 파일 이름 가져오기
    private fun getFileNameFromUri(uri: Uri): String? {
        return contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            cursor.moveToFirst()
            if (nameIndex >= 0) cursor.getString(nameIndex) else null
        }
    }
}