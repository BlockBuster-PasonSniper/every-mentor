package com.wonjun.mentormatch.controller;

import com.wonjun.mentormatch.dto.post.PostResponseDto;
import com.wonjun.mentormatch.dto.post.PostSaveRequestDto;
import com.wonjun.mentormatch.dto.post.PostSimpleResponseDto;
import com.wonjun.mentormatch.dto.post.PostUpdateRequestDto;
import com.wonjun.mentormatch.service.PostService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.List;

@RestController
@RequestMapping("/api/posts")
@RequiredArgsConstructor
@Tag(name = "Post", description = "멘토링 공고 API")
public class PostController {

    private final PostService postService;

    @PostMapping
    @Operation(summary = "공고 생성", description = "멘토가 새로운 멘토링 공고를 작성합니다.")
    public ResponseEntity<Void> createPost(@RequestBody PostSaveRequestDto requestDto) {
        // TODO: Get memberId from SecurityContextHolder after setting up Spring Security
        Long memberId = 1L; // Placeholder for mentor's ID
        Long postId = postService.savePost(memberId, requestDto);
        return ResponseEntity.created(URI.create("/api/posts/" + postId)).build();
    }

    @GetMapping("/{id}")
    @Operation(summary = "공고 단건 조회", description = "특정 멘토링 공고의 상세 정보를 조회합니다.")
    public ResponseEntity<PostResponseDto> getPostById(@PathVariable Long id) {
        PostResponseDto response = postService.findPostById(id);
        return ResponseEntity.ok(response);
    }

    @GetMapping
    @Operation(summary = "공고 전체 조회", description = "모든 멘토링 공고 목록을 조회합니다.")
    public ResponseEntity<List<PostSimpleResponseDto>> getAllPosts() {
        List<PostSimpleResponseDto> responses = postService.findAllPosts();
        return ResponseEntity.ok(responses);
    }

    @PutMapping("/{id}")
    @Operation(summary = "공고 수정", description = "자신이 작성한 멘토링 공고를 수정합니다.")
    public ResponseEntity<Void> updatePost(@PathVariable Long id, @RequestBody PostUpdateRequestDto requestDto) {
        // TODO: Get memberId from SecurityContextHolder
        Long memberId = 1L; // Placeholder for mentor's ID
        postService.updatePost(id, memberId, requestDto);
        return ResponseEntity.ok().build();
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "공고 삭제", description = "자신이 작성한 멘토링 공고를 삭제합니다.")
    public ResponseEntity<Void> deletePost(@PathVariable Long id) {
        // TODO: Get memberId from SecurityContextHolder
        Long memberId = 1L; // Placeholder for mentor's ID
        postService.deletePost(id, memberId);
        return ResponseEntity.noContent().build();
    }
}
