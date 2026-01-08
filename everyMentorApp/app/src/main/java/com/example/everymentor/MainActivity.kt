package com.example.everymentor

import android.os.Bundle
import android.content.Intent
import androidx.appcompat.app.AppCompatActivity
import android.widget.Button



class MainActivity : AppCompatActivity() {
    //main 화면에서 동작될 버튼 or 로그인 화면 버튼 클릭 시 onClickListner 및 기능
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val btnMentor: Button = findViewById(R.id.btnMentor)

        btnMentor.setOnClickListener {
            val intent = Intent(this, MentorActivity::class.java)
            startActivity(intent)
        }

    }
}