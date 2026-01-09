package com.wonjun.mentormatch.domain.member;

import com.wonjun.mentormatch.domain.Member;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Getter
@NoArgsConstructor
public class Certification {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "member_id", nullable = false)
    private Member member;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, columnDefinition = "varchar(255)")
    private CertificationType type;

    @Lob
    @Column(name = "image_base64", nullable = false, columnDefinition="TEXT")
    private String imageBase64;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public Certification(Member member, CertificationType type, String imageBase64) {
        this.member = member;
        this.type = type;
        this.imageBase64 = imageBase64;
    }
}
