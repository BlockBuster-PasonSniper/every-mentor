package com.example.everymentor

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.example.everymentor.R

class LoginActivity : AppCompatActivity() {

    // 하드코딩 계정
    private val VALID_ID = "mentor"
    private val VALID_PW = "1234"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        val etId = findViewById<EditText>(R.id.etId)
        val etPw = findViewById<EditText>(R.id.etPassword)
        val btnLogin = findViewById<Button>(R.id.btnLogin)

        btnLogin.setOnClickListener {
            val id = etId.text.toString().trim()
            val pw = etPw.text.toString().trim()

            if (id == VALID_ID && pw == VALID_PW) {
                val intent = Intent(this, MentorCurriculumActivity::class.java)
                startActivity(intent)
                finish()
            } else {
                Toast.makeText(this, "아이디 또는 비밀번호가 올바르지 않습니다.", Toast.LENGTH_SHORT).show()
            }
        }
    }
}